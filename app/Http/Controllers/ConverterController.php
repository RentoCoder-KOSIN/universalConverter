<?php

namespace App\Http\Controllers;

use App\Exceptions\ConversionException;
use App\Services\ConversionLimiter;
use App\Services\PythonConverter;
use App\Services\WorkspaceCleaner;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;

class ConverterController extends Controller
{
    public function index()
    {
        return view('converter.index', [
            'operations' => config('converter.operations'),
            'maxUploadKb' => config('converter.max_upload_kb'),
        ]);
    }

    public function convert(
        Request $request,
        PythonConverter $converter,
        ConversionLimiter $limiter,
        WorkspaceCleaner $cleaner,
    ) {
        $operations = config('converter.operations');

        // 異常終了などで残った古い一時ファイルを、リクエストのついでに削除する。
        $cleaner->purge((int) config('converter.cleanup_minutes'));

        $messages = [
            'operation.required' => '変換の種類を選んでください。',
            'operation.in' => '未対応の変換の種類です。',
            'file.required' => 'ファイルを選んでください。',
            'file.file' => 'ファイルのアップロードに失敗しました。',
            'file.max' => 'ファイルサイズが上限（:max KB）を超えています。',
            'page.required' => 'PNG にするページ番号を入力してください。',
            'page.integer' => 'ページ番号は整数で入力してください。',
            'page.min' => 'ページ番号は 1 以上を指定してください。',
            'page.max' => 'ページ番号は 50 以下を指定してください。',
        ];

        // アップロードの上限は変換ごとに違うため、先に変換の種類だけを検証する。
        $request->validate([
            'operation' => ['required', 'string', 'in:'.implode(',', array_keys($operations))],
        ], $messages);

        $operationName = $request->input('operation');
        $operation = $operations[$operationName];

        $request->validate([
            'file' => ['required', 'file', 'max:'.($operation['max_upload_kb'] ?? config('converter.max_upload_kb'))],
        ], $messages);

        $pageNumber = null;
        if ($operationName === 'pdf_page_to_png') {
            $request->validate([
                'page' => ['required', 'integer', 'min:1', 'max:50'],
            ], $messages);
            $pageNumber = $request->integer('page');
        }

        $upload = $request->file('file');

        // 拡張子は使い方の案内として確認する。内容の検証は Python 側で行う。
        $extension = strtolower($upload->getClientOriginalExtension());
        if (! in_array($extension, $operation['input_extensions'], true)) {
            return back()
                ->withInput($request->only('operation', 'page'))
                ->withErrors(['file' => $operation['label'].' には .'.implode(' / .', $operation['input_extensions']).' ファイルを選んでください。']);
        }

        // 出力の拡張子。null の変換は入力と同じ拡張子で出力する。
        $outputExtension = $operation['output_extension'] ?? $extension;

        // 保存名は利用者のファイル名を使わず、固定名にする。作業領域は公開ディレクトリの外。
        $workDir = $cleaner->root().'/'.Str::uuid();
        File::makeDirectory($workDir, 0700, true);

        try {
            $inputName = 'input.'.$extension;
            $outputPath = $workDir.'/output.'.$outputExtension;

            $upload->move($workDir, $inputName);

            // 同時実行数の上限を超えているときは、変換を始めずに断る。
            $limiter->run(
                fn () => $converter->convert($operationName, $workDir.'/'.$inputName, $outputPath, $pageNumber),
                $converter->timeoutFor($operationName),
            );

            $contents = File::get($outputPath);
        } catch (ConversionException $e) {
            return back()
                ->withInput($request->only('operation', 'page'))
                ->withErrors(['file' => $e->getMessage()]);
        } finally {
            // 成功・失敗どちらでも一時ファイルを削除する。
            File::deleteDirectory($workDir);
        }

        return response()->streamDownload(
            function () use ($contents) {
                echo $contents;
            },
            $this->downloadName($upload->getClientOriginalName(), $outputExtension),
            ['Content-Type' => $this->contentType($operation['mime'])],
        );
    }

    /**
     * テキスト系の形式にだけ charset を付ける（音声・画像のバイナリには付けない）。
     */
    private function contentType(string $mime): string
    {
        $isText = str_starts_with($mime, 'text/') || $mime === 'application/json';

        return $isText ? $mime.'; charset=UTF-8' : $mime;
    }

    /**
     * ダウンロード名だけに元のファイル名を使う（保存パスには使わない）。
     */
    private function downloadName(string $originalName, string $extension): string
    {
        $base = pathinfo($originalName, PATHINFO_FILENAME);
        // 「backup.tar.gz」のような名前から、出力の拡張子と重なる「.tar」を取り除く
        $base = preg_replace('/\.tar$/i', '', $base) ?? $base;
        $base = preg_replace('/[\x00-\x1F\x7F\/\\\\:*?"<>|]+/u', '_', $base) ?? '';
        $base = trim($base, ' ._');

        if ($base === '') {
            $base = 'converted';
        }

        return Str::limit($base, 100, '').'.'.$extension;
    }
}
