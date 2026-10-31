<?php

namespace Tests\Feature;

use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\File;
use Symfony\Component\Process\Process;
use Tests\TestCase;

/**
 * Laravel → Python（python/converter）まで通した結合テスト。
 * 実行には python3 が使えることが必要（CONVERTER_PYTHON で変更可）。
 */
class ConverterTest extends TestCase
{
    /** 4x3 の赤い PNG */
    private const PNG_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGM8ISfHAANMDEgAhQMAJtoBCkAAOw8AAAAASUVORK5CYII=';

    /** 1 ページ（200 x 100 pt）で、文字「Hello PDF」だけを持つ最小の PDF */
    private const PDF_BASE64 = 'JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCAyMDAgMTAwXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCAzOSA+PgpzdHJlYW0KQlQgL0YxIDI0IFRmIDEwIDQwIFRkIChIZWxsbyBQREYpIFRqIEVUCmVuZHN0cmVhbQplbmRvYmoKNSAwIG9iago8PCAvVHlwZSAvRm9udCAvU3VidHlwZSAvVHlwZTEgL0Jhc2VGb250IC9IZWx2ZXRpY2EgPj4KZW5kb2JqCnhyZWYKMCA2CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAwOSAwMDAwMCBuIAowMDAwMDAwMDU4IDAwMDAwIG4gCjAwMDAwMDAxMTUgMDAwMDAgbiAKMDAwMDAwMDI0MSAwMDAwMCBuIAowMDAwMDAwMzMwIDAwMDAwIG4gCnRyYWlsZXIKPDwgL1NpemUgNiAvUm9vdCAxIDAgUiA+PgpzdGFydHhyZWYKNDAwCiUlRU9GCg==';

    /** Python のモジュールがすべて import できるか（PDF 変換用ライブラリの有無の確認） */
    private function pythonHasModules(string ...$modules): bool
    {
        $process = new Process(
            [config('converter.python'), '-c', 'import '.implode(', ', $modules)],
            config('converter.working_directory'),
        );
        $process->run();

        return $process->isSuccessful();
    }

    /** FFmpeg で 1 秒の短い動画（MP4・音声付き）を作る。作れなければ null。 */
    private function makeVideoBytes(): ?string
    {
        $path = sys_get_temp_dir().'/conv_test_'.bin2hex(random_bytes(4)).'.mp4';

        $process = new Process([
            'ffmpeg', '-v', 'error',
            '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', $path,
        ]);
        $process->setTimeout(60);

        try {
            $process->run();

            return $process->isSuccessful() ? file_get_contents($path) : null;
        } finally {
            @unlink($path);
        }
    }

    /** @param array<string, string> $entries 名前 => 内容 */
    private function zipBytes(array $entries): string
    {
        $path = sys_get_temp_dir().'/conv_test_'.bin2hex(random_bytes(4)).'.zip';
        $zip = new \ZipArchive();
        $zip->open($path, \ZipArchive::CREATE | \ZipArchive::OVERWRITE);

        foreach ($entries as $name => $content) {
            $zip->addFromString($name, $content);
        }

        $zip->close();

        try {
            return file_get_contents($path);
        } finally {
            @unlink($path);
        }
    }

    /** ZIP のバイト列を開いて、エントリー名の一覧を返す。 */
    private function zipEntryNames(string $bytes): array
    {
        $path = sys_get_temp_dir().'/conv_test_'.bin2hex(random_bytes(4)).'.zip';
        file_put_contents($path, $bytes);

        try {
            $zip = new \ZipArchive();
            $this->assertTrue($zip->open($path) === true, '出力が ZIP として開けない');
            $names = [];

            for ($i = 0; $i < $zip->numFiles; $i++) {
                $names[] = $zip->getNameIndex($i);
            }

            $zip->close();

            return $names;
        } finally {
            @unlink($path);
        }
    }

    private function pythonHasPillow(): bool
    {
        $process = new Process([config('converter.python'), '-c', 'import PIL'], config('converter.working_directory'));
        $process->run();

        return $process->isSuccessful();
    }


    private function ffmpegAvailable(): bool
    {
        foreach (['ffmpeg', 'ffprobe'] as $tool) {
            $process = new Process([$tool, '-version']);

            try {
                $process->run();
            } catch (\Throwable) {
                return false;
            }

            if (! $process->isSuccessful()) {
                return false;
            }
        }

        return true;
    }

    /** 440Hz のモノラル 16bit WAV を 0.5 秒分作る。 */
    private function wavBytes(): string
    {
        $rate = 8000;
        $samples = '';

        for ($i = 0; $i < $rate / 2; $i++) {
            $samples .= pack('v', (int) (sin(2 * M_PI * 440 * $i / $rate) * 12000) & 0xFFFF);
        }

        return 'RIFF'.pack('V', 36 + strlen($samples)).'WAVEfmt '.pack('VvvVVvv', 16, 1, 1, $rate, $rate * 2, 2, 16)
            .'data'.pack('V', strlen($samples)).$samples;
    }

    private function remainingWorkDirs(): array
    {
        $dir = storage_path('app/private/converter');

        return File::isDirectory($dir) ? File::directories($dir) : [];
    }

    private function upload(string $name, string $content): UploadedFile
    {
        return UploadedFile::fake()->createWithContent($name, $content);
    }

    public function test_form_is_displayed(): void
    {
        $this->get('/converter')
            ->assertOk()
            ->assertSee('CSV → JSON')
            ->assertSee('JSON → CSV');
    }

    public function test_csv_is_converted_to_json_and_downloaded(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('students.csv', "name,age\n田中,18\n"),
        ]);

        $response->assertOk();
        $response->assertDownload('students.json');

        $this->assertSame(
            [['name' => '田中', 'age' => '18']],
            json_decode($response->streamedContent(), true),
        );
    }

    public function test_japanese_file_name_is_kept_in_download_name(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('生徒.csv', "name\n田中\n"),
        ]);

        // 日本語名は Content-Disposition の filename*（UTF-8 エンコード）に入る
        $this->assertStringContainsString(
            rawurlencode('生徒.json'),
            $response->headers->get('Content-Disposition'),
        );
    }

    public function test_json_is_converted_to_csv(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'json_to_csv',
            'file' => $this->upload('data.json', '[{"name":"田中","age":18}]'),
        ]);

        $response->assertDownload('data.csv');
        $this->assertStringContainsString("name,age\n田中,18", str_replace("\r\n", "\n", $response->streamedContent()));
    }

    public function test_file_is_required(): void
    {
        $this->post('/converter', ['operation' => 'csv_to_json'])
            ->assertSessionHasErrors('file');
    }

    public function test_unknown_operation_is_rejected(): void
    {
        $this->post('/converter', [
            'operation' => 'rm_rf',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ])->assertSessionHasErrors('operation');
    }

    public function test_wrong_extension_is_rejected(): void
    {
        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.json', '[]'),
        ])->assertSessionHasErrors('file');
    }

    public function test_oversized_file_is_rejected(): void
    {
        config(['converter.max_upload_kb' => 1]);

        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => UploadedFile::fake()->create('a.csv', 10, 'text/csv'),
        ])->assertSessionHasErrors('file');
    }

    public function test_invalid_content_shows_error_without_internal_details(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'json_to_csv',
            'file' => $this->upload('a.json', '{not json'),
        ]);

        $response->assertSessionHasErrors('file');

        $message = session('errors')->first('file');
        $this->assertStringNotContainsString(storage_path(), $message);
        $this->assertStringNotContainsString('Traceback', $message);
    }

    public function test_missing_python_shows_generic_error(): void
    {
        config(['converter.python' => '/nonexistent/python']);

        $response = $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ]);

        $response->assertSessionHasErrors('file');
        $this->assertStringNotContainsString('/nonexistent', session('errors')->first('file'));
    }

    public function test_temp_files_are_removed_after_success_and_failure(): void
    {
        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ]);
        $this->post('/converter', [
            'operation' => 'json_to_csv',
            'file' => $this->upload('a.json', '{not json'),
        ]);

        $dir = storage_path('app/private/converter');
        $remaining = File::isDirectory($dir) ? File::directories($dir) : [];

        $this->assertSame([], $remaining);
    }

    public function test_config_operations_match_python_registry(): void
    {
        $process = new Process(
            [config('converter.python'), '-c', 'import json; from converter.registry import operation_names; print(json.dumps(operation_names()))'],
            config('converter.working_directory'),
        );
        $process->mustRun();

        $registered = json_decode($process->getOutput(), true);
        $configured = array_keys(config('converter.operations'));

        sort($configured);

        // 設定にあるのに Python に無い（実行時エラーになる）／Python にあるのに画面に出ない、を防ぐ
        $this->assertSame($registered, $configured);
    }

    public function test_json_is_formatted(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'json_format',
            'file' => $this->upload('data.json', '{"name":"田中","age":18}'),
        ]);

        $response->assertDownload('data.json');
        $this->assertSame("{\n  \"name\": \"田中\",\n  \"age\": 18\n}\n", $response->streamedContent());
    }

    public function test_invalid_json_is_rejected_by_formatter(): void
    {
        $this->post('/converter', [
            'operation' => 'json_format',
            'file' => $this->upload('data.json', '{not json'),
        ])->assertSessionHasErrors('file');
    }

    public function test_shift_jis_csv_is_converted_to_utf8_and_keeps_extension(): void
    {
        $sjis = mb_convert_encoding("名前,年齢\r\n田中,18\r\n", 'SJIS-win', 'UTF-8');

        $response = $this->post('/converter', [
            'operation' => 'txt_to_utf8',
            'file' => $this->upload('students.csv', $sjis),
        ]);

        $response->assertDownload('students.csv');
        $this->assertSame("名前,年齢\r\n田中,18\r\n", $response->streamedContent());
    }

    public function test_image_is_converted(): void
    {
        if (! $this->pythonHasPillow()) {
            $this->markTestSkipped('Python に Pillow が入っていないためスキップ（pip install -r python/requirements.txt）');
        }

        $response = $this->post('/converter', [
            'operation' => 'image_to_jpeg',
            'file' => $this->upload('photo.png', base64_decode(self::PNG_BASE64)),
        ]);

        $response->assertDownload('photo.jpg');

        $content = $response->streamedContent();
        $this->assertStringStartsWith("\xFF\xD8\xFF", $content); // JPEG のシグネチャ
    }

    public function test_non_image_file_with_image_extension_is_rejected(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'image_to_png',
            'file' => $this->upload('fake.png', 'これは画像ではありません'),
        ]);

        $response->assertSessionHasErrors('file');
        $this->assertStringNotContainsString(storage_path(), session('errors')->first('file'));
    }

    // ---- 音声 ----

    public function test_form_lists_audio_operations(): void
    {
        $this->get('/converter')
            ->assertOk()
            ->assertSee('音声 → MP3')
            ->assertSee('音声 → FLAC');
    }

    public function test_audio_is_converted_without_charset_in_content_type(): void
    {
        if (! $this->ffmpegAvailable()) {
            $this->markTestSkipped('FFmpeg が使えないためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'audio_to_flac',
            'file' => $this->upload('tone.wav', $this->wavBytes()),
        ]);

        $response->assertDownload('tone.flac');
        $this->assertStringStartsWith('fLaC', $response->streamedContent()); // FLAC のシグネチャ
        $this->assertStringNotContainsString('charset', $response->headers->get('Content-Type'));
    }

    public function test_audio_is_converted_to_ogg_and_mp3(): void
    {
        if (! $this->ffmpegAvailable()) {
            $this->markTestSkipped('FFmpeg が使えないためスキップ');
        }

        $ogg = $this->post('/converter', [
            'operation' => 'audio_to_ogg',
            'file' => $this->upload('tone.wav', $this->wavBytes()),
        ]);
        $ogg->assertDownload('tone.ogg');
        $this->assertStringStartsWith('OggS', $ogg->streamedContent());

        $mp3 = $this->post('/converter', [
            'operation' => 'audio_to_mp3',
            'file' => $this->upload('tone.wav', $this->wavBytes()),
        ]);
        $mp3->assertDownload('tone.mp3');
        $content = $mp3->streamedContent();
        $this->assertTrue(str_starts_with($content, 'ID3') || str_starts_with($content, "\xFF"));
    }

    public function test_non_audio_file_with_audio_extension_is_rejected(): void
    {
        if (! $this->ffmpegAvailable()) {
            $this->markTestSkipped('FFmpeg が使えないためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'audio_to_mp3',
            'file' => $this->upload('fake.mp3', 'これは音声ではありません'),
        ]);

        $response->assertSessionHasErrors('file');
        $this->assertStringNotContainsString(storage_path(), session('errors')->first('file'));
        $this->assertSame([], $this->remainingWorkDirs());
    }

    public function test_audio_operation_rejects_other_extensions(): void
    {
        $this->post('/converter', [
            'operation' => 'audio_to_mp3',
            'file' => $this->upload('photo.png', base64_decode(self::PNG_BASE64)),
        ])->assertSessionHasErrors('file');
    }

    // ---- 同時実行数の制限・一時ファイル ----

    public function test_request_is_refused_while_all_slots_are_busy(): void
    {
        config(['converter.max_concurrent' => 1]);

        $busy = Cache::lock('converter:slot:0', 30);
        $this->assertTrue($busy->get());

        try {
            $response = $this->post('/converter', [
                'operation' => 'csv_to_json',
                'file' => $this->upload('a.csv', "a\n1\n"),
            ]);

            $response->assertSessionHasErrors('file');
            $this->assertStringContainsString('混み合', session('errors')->first('file'));
            $this->assertSame([], $this->remainingWorkDirs());
        } finally {
            $busy->release();
        }

        // 空いたら通常どおり変換できる
        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ])->assertDownload('a.json');
    }

    public function test_slot_is_released_after_a_failed_conversion(): void
    {
        config(['converter.max_concurrent' => 1]);

        $this->post('/converter', [
            'operation' => 'json_to_csv',
            'file' => $this->upload('a.json', '{not json'),
        ])->assertSessionHasErrors('file');

        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ])->assertDownload('a.json');
    }

    public function test_stale_work_directories_are_removed_on_next_request(): void
    {
        $stale = storage_path('app/private/converter/stale-test-dir');
        File::makeDirectory($stale, 0700, true, true);
        File::put($stale.'/input.csv', 'x');
        touch($stale, time() - 3 * 3600);

        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ]);

        $this->assertFalse(File::isDirectory($stale));
    }

    // ---- PDF ----

    public function test_pdf_text_is_extracted(): void
    {
        if (! $this->pythonHasModules('pypdf')) {
            $this->markTestSkipped('Python に pypdf が入っていないためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'pdf_to_txt',
            'file' => $this->upload('doc.pdf', base64_decode(self::PDF_BASE64)),
        ]);

        $response->assertDownload('doc.txt');
        $this->assertStringContainsString('Hello PDF', $response->streamedContent());
    }

    public function test_pdf_first_page_is_rendered_as_png(): void
    {
        if (! $this->pythonHasModules('pypdfium2', 'PIL')) {
            $this->markTestSkipped('Python に pypdfium2 / Pillow が入っていないためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'pdf_first_page_to_png',
            'file' => $this->upload('doc.pdf', base64_decode(self::PDF_BASE64)),
        ]);

        $response->assertDownload('doc.png');
        $this->assertStringStartsWith("\x89PNG", $response->streamedContent());
    }

    public function test_pdf_pages_are_zipped_as_png(): void
    {
        if (! $this->pythonHasModules('pypdfium2', 'PIL') || ! class_exists(\ZipArchive::class)) {
            $this->markTestSkipped('PDF の画像化ライブラリまたは ZipArchive が無いためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'pdf_to_png_zip',
            'file' => $this->upload('doc.pdf', base64_decode(self::PDF_BASE64)),
        ]);

        $response->assertDownload('doc.zip');
        $this->assertSame(['page_001.png'], $this->zipEntryNames($response->streamedContent()));
    }

    public function test_image_is_converted_to_pdf(): void
    {
        if (! $this->pythonHasModules('PIL')) {
            $this->markTestSkipped('Python に Pillow が入っていないためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'image_to_pdf',
            'file' => $this->upload('scan.png', base64_decode(self::PNG_BASE64)),
        ]);

        $response->assertDownload('scan.pdf');
        $this->assertStringStartsWith('%PDF-', $response->streamedContent());
    }

    public function test_non_pdf_file_with_pdf_extension_is_rejected(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'pdf_to_txt',
            'file' => $this->upload('fake.pdf', 'これは PDF ではありません'),
        ]);

        $response->assertSessionHasErrors('file');
        $this->assertStringNotContainsString(storage_path(), session('errors')->first('file'));
        $this->assertSame([], $this->remainingWorkDirs());
    }

    // ---- 動画 ----

    public function test_video_is_converted_to_mp4_and_webm(): void
    {
        if (! $this->ffmpegAvailable()) {
            $this->markTestSkipped('FFmpeg / ffprobe が無いためスキップ');
        }

        $video = $this->makeVideoBytes();
        $this->assertNotNull($video, 'テスト用の動画を作れなかった');

        $mp4 = $this->post('/converter', [
            'operation' => 'video_to_mp4',
            'file' => $this->upload('clip.mp4', $video),
        ]);
        $mp4->assertDownload('clip.mp4');
        $this->assertSame('ftyp', substr($mp4->streamedContent(), 4, 4)); // MP4 のシグネチャ
        $this->assertSame('video/mp4', $mp4->headers->get('Content-Type'));

        $webm = $this->post('/converter', [
            'operation' => 'video_to_webm',
            'file' => $this->upload('clip.mp4', $video),
        ]);
        $webm->assertDownload('clip.webm');
        $this->assertStringStartsWith("\x1A\x45\xDF\xA3", $webm->streamedContent()); // EBML（WebM）のシグネチャ
    }

    public function test_audio_can_be_extracted_from_video(): void
    {
        if (! $this->ffmpegAvailable()) {
            $this->markTestSkipped('FFmpeg / ffprobe が無いためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'video_extract_audio',
            'file' => $this->upload('clip.mp4', $this->makeVideoBytes()),
        ]);

        $response->assertDownload('clip.mp3');
        $this->assertSame('audio/mpeg', $response->headers->get('Content-Type'));
        $this->assertNotSame('', $response->streamedContent());
    }

    public function test_non_video_file_with_video_extension_is_rejected(): void
    {
        $response = $this->post('/converter', [
            'operation' => 'video_to_mp4',
            'file' => $this->upload('fake.mp4', 'これは動画ではありません'),
        ]);

        $response->assertSessionHasErrors('file');
        $this->assertStringNotContainsString(storage_path(), session('errors')->first('file'));
        $this->assertSame([], $this->remainingWorkDirs());
    }

    public function test_video_operation_rejects_audio_extension(): void
    {
        $this->post('/converter', [
            'operation' => 'video_to_mp4',
            'file' => $this->upload('song.mp3', $this->wavBytes()),
        ])->assertSessionHasErrors('file');
    }

    // ---- アーカイブ ----

    public function test_zip_is_converted_to_targz_and_back(): void
    {
        if (! class_exists(\ZipArchive::class)) {
            $this->markTestSkipped('ZipArchive が無いためスキップ');
        }

        $targz = $this->post('/converter', [
            'operation' => 'zip_to_targz',
            'file' => $this->upload('files.zip', $this->zipBytes(['a.txt' => 'A', 'docs/メモ.txt' => 'こんにちは'])),
        ]);

        $targz->assertDownload('files.tar.gz');
        $content = $targz->streamedContent();
        $this->assertStringStartsWith("\x1F\x8B", $content); // gzip のシグネチャ

        $back = $this->post('/converter', [
            'operation' => 'targz_to_zip',
            'file' => $this->upload('files.tar.gz', $content),
        ]);

        // 「files.tar.gz」の「.tar」は取り除かれ、「files.zip」になる
        $back->assertDownload('files.zip');

        $names = $this->zipEntryNames($back->streamedContent());
        sort($names);
        $this->assertSame(['a.txt', 'docs/メモ.txt'], $names);
    }

    public function test_zip_with_path_traversal_is_rejected(): void
    {
        if (! class_exists(\ZipArchive::class)) {
            $this->markTestSkipped('ZipArchive が無いためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'zip_to_targz',
            'file' => $this->upload('evil.zip', $this->zipBytes(['../evil.txt' => 'x'])),
        ]);

        $response->assertSessionHasErrors('file');
        $this->assertSame([], $this->remainingWorkDirs());
    }

    public function test_zip_info_lists_entries_as_json(): void
    {
        if (! class_exists(\ZipArchive::class)) {
            $this->markTestSkipped('ZipArchive が無いためスキップ');
        }

        $response = $this->post('/converter', [
            'operation' => 'zip_info',
            'file' => $this->upload('files.zip', $this->zipBytes(['a.txt' => 'AB', 'b.txt' => 'CDE'])),
        ]);

        $response->assertDownload('files.json');
        $info = json_decode($response->streamedContent(), true);
        $this->assertSame(2, $info['count']);
        $this->assertSame(5, $info['total_size']);
    }

    public function test_non_archive_file_is_rejected(): void
    {
        $this->post('/converter', [
            'operation' => 'zip_to_targz',
            'file' => $this->upload('fake.zip', 'これは ZIP ではありません'),
        ])->assertSessionHasErrors('file');

        $this->post('/converter', [
            'operation' => 'targz_to_zip',
            'file' => $this->upload('fake.gz', 'これは tar.gz ではありません'),
        ])->assertSessionHasErrors('file');

        $this->assertSame([], $this->remainingWorkDirs());
    }

    // ---- 変換ごとの上限 ----

    public function test_upload_limit_can_be_set_per_operation(): void
    {
        config(['converter.operations.pdf_to_txt.max_upload_kb' => 1]);

        // 1 KB を超える PDF は、この変換だけ断られる
        $this->post('/converter', [
            'operation' => 'pdf_to_txt',
            'file' => UploadedFile::fake()->create('big.pdf', 10, 'application/pdf'),
        ])->assertSessionHasErrors('file');

        // 他の変換の上限（既定）には影響しない
        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ])->assertDownload('a.json');
    }

    public function test_heavy_operations_have_their_own_timeout_and_upload_limit(): void
    {
        $converter = app(\App\Services\PythonConverter::class);

        $this->assertSame(120, $converter->timeoutFor('video_to_mp4'));
        $this->assertSame((int) config('converter.timeout'), $converter->timeoutFor('csv_to_json'));

        $this->assertGreaterThan(
            (int) config('converter.max_upload_kb'),
            config('converter.operations.video_to_mp4.max_upload_kb'),
        );
    }

    public function test_form_shows_limits_per_group(): void
    {
        $this->get('/converter')
            ->assertOk()
            ->assertSee('動画 30 MB')
            ->assertSee('PDF 10 MB')
            ->assertSee('PDF → テキスト')
            ->assertSee('ZIP → tar.gz');
    }

    public function test_form_option_values_are_the_operation_keys(): void
    {
        // 画面の選択肢の value が、そのままフォームから送られる。変換名と一致していないと
        // 「未対応の変換の種類です」になる（グループ化で連番に振り直されたことがあった）。
        $html = $this->get('/converter')->assertOk()->getContent();

        preg_match_all('/<input type="radio" name="operation" value="([^"]*)"/', $html, $matches);

        $expected = array_keys(config('converter.operations'));
        $actual = $matches[1];

        sort($expected);
        sort($actual);

        $this->assertSame($expected, $actual);
    }

    public function test_every_operation_in_the_form_is_accepted_by_the_server(): void
    {
        $html = $this->get('/converter')->assertOk()->getContent();

        preg_match_all('/<input type="radio" name="operation" value="([^"]*)"/', $html, $matches);

        foreach ($matches[1] as $value) {
            // ファイルは付けない。「変換の種類」が受理されれば、エラーはファイルについてだけになる。
            $response = $this->post('/converter', ['operation' => $value]);

            $response->assertSessionHasErrors('file');
            $response->assertSessionDoesntHaveErrors('operation');
        }
    }

    // ---- 失敗の原因が分かること ----

    public function test_missing_tool_is_explained_as_unavailable(): void
    {
        // Laravel が .env の値を子プロセスに渡すのと同じ経路（$_ENV）で設定する
        $_ENV['CONVERTER_FFMPEG'] = '/nonexistent/ffmpeg';

        try {
            $this->post('/converter', [
                'operation' => 'video_to_mp4',
                'file' => $this->upload('clip.mp4', 'dummy'),
            ])->assertSessionHasErrors('file');

            $message = session('errors')->first('file');
            $this->assertStringContainsString('現在利用できません', $message);
            $this->assertStringNotContainsString('/nonexistent', $message);
        } finally {
            unset($_ENV['CONVERTER_FFMPEG']);
        }
    }

    public function test_python_crash_without_json_logs_stderr_tail_but_not_to_the_user(): void
    {
        $script = sys_get_temp_dir().'/fake_python_'.bin2hex(random_bytes(4)).'.sh';
        file_put_contents($script, "#!/bin/sh\necho 'ModuleNotFoundError: No module named boom' >&2\nexit 1\n");
        chmod($script, 0755);
        config(['converter.python' => $script, 'app.debug' => false]);

        \Illuminate\Support\Facades\Log::spy();

        try {
            $this->post('/converter', [
                'operation' => 'csv_to_json',
                'file' => $this->upload('a.csv', "a\n1\n"),
            ])->assertSessionHasErrors('file');

            $message = session('errors')->first('file');
            $this->assertStringNotContainsString('boom', $message);
            $this->assertStringNotContainsString('laravel.log', $message);

            \Illuminate\Support\Facades\Log::shouldHaveReceived('warning')
                ->withArgs(fn ($text, $context) => $text === 'converter: failed'
                    && str_contains($context['stderr_tail'] ?? '', 'No module named boom'))
                ->once();
        } finally {
            @unlink($script);
        }
    }

    public function test_debug_mode_points_to_the_log_for_generic_errors(): void
    {
        config(['converter.python' => '/nonexistent/python', 'app.debug' => true]);

        $this->post('/converter', [
            'operation' => 'csv_to_json',
            'file' => $this->upload('a.csv', "a\n1\n"),
        ])->assertSessionHasErrors('file');

        $this->assertStringContainsString('laravel.log', session('errors')->first('file'));
    }
}
