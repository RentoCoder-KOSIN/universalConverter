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
class ConverterService
{
    private const GENERIC_ERROR = '変換に失敗しました。時間をおいて再度お試しください。';

    /**
     * @throws ConversionException
     */
    public function convert(string $operation, string $inputPath, string $outputPath): void
    {
        if (! array_key_exists($operation, config('converter.operations'))) {
            throw new ConversionException('未対応の変換形式です。');
        }

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
            ['PYTHONIOENCODING' => 'utf-8', 'PYTHONUTF8' => '1'],
            null,
            (float) config('converter.timeout'),
        );

        try {
            $process->run();
        } catch (ProcessTimedOutException) {
            Log::warning('converter: timeout', ['operation' => $operation]);
            throw new ConversionException('変換に時間がかかりすぎたため中止しました。');
        } catch (ProcessException $e) {
            // 起動失敗（Python が見つからない等）。詳細はログにだけ残す。
            Log::error('converter: process failed to start', ['operation' => $operation, 'exception' => $e::class]);
            throw new ConversionException(self::GENERIC_ERROR);
        }

        $result = json_decode($process->getOutput(), true);

        if ($process->isSuccessful() && is_array($result) && ($result['success'] ?? false) === true) {
            return;
        }

        // ファイル内容や内部パスはログに出さない。操作名・終了コード・エラー種別だけ記録する。
        Log::warning('converter: failed', [
            'operation' => $operation,
            'exit_code' => $process->getExitCode(),
            'code' => is_array($result) ? ($result['code'] ?? null) : null,
        ]);

        // 入力内容に起因するエラーだけは、そのまま利用者に見せる。
        if (is_array($result) && ($result['code'] ?? null) === 'invalid_input' && is_string($result['error'] ?? null)) {
            throw new ConversionException('ファイルの内容を変換できませんでした: '.$result['error']);
        }

        throw new ConversionException(self::GENERIC_ERROR);
    }
}
