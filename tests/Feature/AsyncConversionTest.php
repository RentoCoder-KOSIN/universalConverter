<?php

namespace Tests\Feature;

use App\Jobs\ProcessConversion;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Str;
use Tests\TestCase;

class AsyncConversionTest extends TestCase
{
    public function test_long_conversion_is_queued_and_exposes_only_its_status(): void
    {
        Queue::fake([ProcessConversion::class]);

        $response = $this->withHeader('Accept', 'application/json')->post('/converter', [
            'operation' => 'audio_to_text',
            'file' => UploadedFile::fake()->create('speech.wav', 20, 'audio/wav'),
        ]);

        $response->assertAccepted()
            ->assertJsonStructure(['status', 'status_url', 'download_url']);

        $workDirectory = null;
        Queue::assertPushed(ProcessConversion::class, function (ProcessConversion $job) use (&$workDirectory): bool {
            $workDirectory = $job->task['work_dir'];

            return $job->task['operation'] === 'audio_to_text';
        });
        $this->assertDirectoryExists($workDirectory);

        $taskId = basename($response->json('status_url'));
        $this->getJson(route('converter.status', $taskId))
            ->assertOk()
            ->assertExactJson(['status' => 'queued']);

        $this->assertStringNotContainsString(storage_path(), $response->getContent());
        File::deleteDirectory($workDirectory);
        Cache::forget('converter:task:'.$taskId);
    }

    public function test_unknown_async_conversion_status_is_not_found(): void
    {
        $this->getJson(route('converter.status', '00000000-0000-4000-8000-000000000000'))
            ->assertNotFound();
    }

    public function test_json_request_receives_conversion_errors_instead_of_a_redirect(): void
    {
        $response = $this->withHeader('Accept', 'application/json')->post('/converter', [
            'operation' => 'json_to_csv',
            'file' => UploadedFile::fake()->createWithContent('broken.json', '{invalid'),
        ]);

        $response->assertUnprocessable();
        $this->assertStringStartsWith('ファイルの内容を変換できませんでした: ', $response->json('message'));
    }

    public function test_completed_async_conversion_download_removes_its_temporary_files(): void
    {
        $taskId = (string) Str::uuid();
        $workDirectory = storage_path('app/private/converter/'.$taskId);
        File::makeDirectory($workDirectory, 0700, true);
        File::put($workDirectory.'/output.txt', "変換結果\n");
        Cache::put('converter:task:'.$taskId, [
            'status' => 'completed',
            'work_dir' => $workDirectory,
            'output_path' => $workDirectory.'/output.txt',
            'download_name' => 'result.txt',
            'mime' => 'text/plain',
        ], now()->addHour());

        $response = $this->get(route('converter.download', $taskId));

        $response->assertDownload('result.txt');
        $this->assertSame("変換結果\n", $response->streamedContent());
        $this->assertDirectoryDoesNotExist($workDirectory);
        $this->assertFalse(Cache::has('converter:task:'.$taskId));
    }
}
