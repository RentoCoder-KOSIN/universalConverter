<?php

namespace App\Services;

use App\Exceptions\ConversionException;
use Illuminate\Support\Facades\Log;
use Symfony\Component\Process\Exception\ExceptionInterface as ProcessException;
use Symfony\Component\Process\Exception\ProcessTimedOutException;
use Symfony\Component\Process\Process;

/**
 * Python の変換エンジン（python/converter）を呼び出す。
 *
 * 入出力の契約:
 *   実行: <python> -m converter.main <operation> <input> <output>
 *   成功: 終了コード 0 / stdout に {"success": true, "output": "..."}
 *   失敗: 終了コード 1 / stdout に {"success": false, "code": "invalid_input"|"io_error", "error": "..."}
 */
class PythonConverter
{
    private const GENERIC_ERROR = '変換に失敗しました。時間をおいて再度お試しください。';

    /**
     * その変換に許す秒数。変換ごとの設定（動画など重い処理）があればそれを、無ければ全体の設定を使う。
     */
    public function timeoutFor(string $operation): int
    {
        $timeout = config("converter.operations.{$operation}.timeout") ?? config('converter.timeout');

        return max(1, (int) $timeout);
    }

    /**
     * @throws ConversionException
     */
    public function convert(string $operation, string $inputPath, string $outputPath): void
    {
        if (! array_key_exists($operation, config('converter.operations'))) {
            throw new ConversionException('未対応の変換形式です。');
        }

        $timeout = $this->timeoutFor($operation);

        // シェル文字列を組み立てず、引数配列で起動する。
        $process = new Process(
            [
                config('converter.python'),
                '-m', 'converter.main',
                $operation,
                $inputPath,
                $outputPath,
            ],
            config('converter.working_directory'),
            // Windows などの文字コード設定に左右されないよう UTF-8 に固定する。
            [
                'PYTHONIOENCODING' => 'utf-8',
                'PYTHONUTF8' => '1',
                // FFmpeg は Laravel のタイムアウトより先に自分で止まるようにする。
                // （Python を強制終了しても、子プロセスの FFmpeg が残らないようにするため）
                'CONVERTER_FFMPEG_TIMEOUT' => (string) max(1, $timeout - 5),
            ],
            null,
            (float) $timeout,
        );

        try {
            $process->run();
        } catch (ProcessTimedOutException) {
            Log::warning('converter: timeout', ['operation' => $operation]);
            throw new ConversionException('変換に時間がかかりすぎたため中止しました。');
        } catch (ProcessException $e) {
            // 起動失敗（Python が見つからない等）。詳細はログにだけ残す。
            Log::error('converter: process failed to start', ['operation' => $operation, 'exception' => $e::class]);
            throw new ConversionException($this->genericError());
        }

        $result = json_decode($process->getOutput(), true);

        if ($process->isSuccessful() && is_array($result) && ($result['success'] ?? false) === true) {
            return;
        }

        // ファイル内容や内部パスはログに出さない。操作名・終了コード・エラー種別だけ記録する。
        $context = [
            'operation' => $operation,
            'exit_code' => $process->getExitCode(),
            'code' => is_array($result) ? ($result['code'] ?? null) : null,
        ];

        // 変換エンジンが結果の JSON を返さずに終了した（Python が import に失敗した等）ときだけ、
        // 原因の手がかりとして標準エラーの末尾（最後の 300 文字）を残す。
        if (! is_array($result)) {
            $context['stderr_tail'] = mb_scrub(mb_substr(trim($process->getErrorOutput()), -300));
        }

        Log::warning('converter: failed', $context);

        // 入力内容に起因するエラーだけは、そのまま利用者に見せる。
        if (is_array($result) && ($result['code'] ?? null) === 'invalid_input' && is_string($result['error'] ?? null)) {
            throw new ConversionException('ファイルの内容を変換できませんでした: '.$result['error']);
        }

        // ライブラリや FFmpeg が入っていない。利用者ではなく、サーバーの設定の問題。
        if (is_array($result) && ($result['code'] ?? null) === 'unavailable') {
            throw new ConversionException('この変換は、サーバーに必要なライブラリまたはツール（Pillow・pypdf・FFmpeg など）が入っていないため、現在利用できません。');
        }

        throw new ConversionException($this->genericError());
    }

    /**
     * 原因を伏せた汎用メッセージ。開発モードのときだけ、原因を調べる場所を案内する。
     */
    private function genericError(): string
    {
        if (config('app.debug')) {
            return self::GENERIC_ERROR.'（開発モード: storage/logs/laravel.log の「converter:」の行に原因が出ています）';
        }

        return self::GENERIC_ERROR;
    }
}
