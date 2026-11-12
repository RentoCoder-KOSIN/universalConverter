<?php

namespace App\Jobs;

use App\Exceptions\ConversionException;
use App\Services\ConversionLimiter;
use App\Services\PythonConverter;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\File;
use Throwable;

class ProcessConversion implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $tries = 1;

    public int $timeout = 330;

    /**
     * Create a new job instance.
     */
    /**
     * @param array{operation: string, input_path: string, output_path: string, work_dir: string} $task
     */
    public function __construct(public string $taskId, public array $task) {}

    /**
     * Execute the job.
     */
    public function handle(PythonConverter $converter, ConversionLimiter $limiter): void
    {
        $this->updateStatus(['status' => 'processing']);

        try {
            $limiter->run(
                fn () => $converter->convert(
                    $this->task['operation'],
                    $this->task['input_path'],
                    $this->task['output_path'],
                ),
                $converter->timeoutFor($this->task['operation']),
            );

            $this->updateStatus(['status' => 'completed']);
        } catch (ConversionException $exception) {
            File::deleteDirectory($this->task['work_dir']);
            $this->updateStatus(['status' => 'failed', 'message' => $exception->getMessage()]);
        }
    }

    public function failed(?Throwable $exception): void
    {
        File::deleteDirectory($this->task['work_dir']);
        $this->updateStatus([
            'status' => 'failed',
            'message' => '処理中にエラーが発生しました。ファイルを選び直して、もう一度お試しください。',
        ]);
    }

    /** @param array<string, string> $updates */
    private function updateStatus(array $updates): void
    {
        $key = 'converter:task:'.$this->taskId;
        $task = Cache::get($key);

        if (is_array($task)) {
            Cache::put($key, array_merge($task, $updates), now()->addHour());
        }
    }
}
