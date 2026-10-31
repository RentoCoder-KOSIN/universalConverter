<?php

namespace Tests\Feature;

use App\Services\WorkspaceCleaner;
use Illuminate\Support\Facades\File;
use Tests\TestCase;

class WorkspaceCleanerTest extends TestCase
{
    private array $created = [];

    protected function tearDown(): void
    {
        foreach ($this->created as $directory) {
            File::deleteDirectory($directory);
        }

        parent::tearDown();
    }

    private function makeDirectory(string $name, int $ageMinutes): string
    {
        $directory = app(WorkspaceCleaner::class)->root().'/'.$name;
        File::makeDirectory($directory, 0700, true, true);
        File::put($directory.'/input.txt', 'x');
        touch($directory, time() - $ageMinutes * 60);

        return $this->created[] = $directory;
    }

    public function test_only_old_directories_are_removed(): void
    {
        $old = $this->makeDirectory('cleaner-test-old', 120);
        $fresh = $this->makeDirectory('cleaner-test-fresh', 1);

        $removed = app(WorkspaceCleaner::class)->purge(60);

        $this->assertGreaterThanOrEqual(1, $removed);
        $this->assertFalse(File::isDirectory($old));
        $this->assertTrue(File::isDirectory($fresh));
    }

    public function test_purge_without_work_root_does_nothing(): void
    {
        $cleaner = new class extends WorkspaceCleaner
        {
            public function root(): string
            {
                return sys_get_temp_dir().'/converter-root-that-does-not-exist-'.uniqid();
            }
        };

        $this->assertSame(0, $cleaner->purge(60));
    }

    public function test_cleanup_command_removes_old_directories(): void
    {
        $old = $this->makeDirectory('cleaner-test-command-old', 200);
        $fresh = $this->makeDirectory('cleaner-test-command-fresh', 1);

        $this->artisan('converter:cleanup', ['--minutes' => 60])->assertSuccessful();

        $this->assertFalse(File::isDirectory($old));
        $this->assertTrue(File::isDirectory($fresh));
    }

    public function test_cleanup_command_uses_configured_minutes_by_default(): void
    {
        config(['converter.cleanup_minutes' => 30]);
        $old = $this->makeDirectory('cleaner-test-config-old', 45);

        $this->artisan('converter:cleanup')->assertSuccessful();

        $this->assertFalse(File::isDirectory($old));
    }
}
