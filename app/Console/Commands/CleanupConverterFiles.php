<?php

namespace App\Console\Commands;

use App\Services\WorkspaceCleaner;
use Illuminate\Console\Command;

class CleanupConverterFiles extends Command
{
    protected $signature = 'converter:cleanup {--minutes= : この分数より古い作業ディレクトリを削除する（既定: CONVERTER_CLEANUP_MINUTES）}';

    protected $description = '変換の作業ディレクトリに残った古い一時ファイルを削除する';

    public function handle(WorkspaceCleaner $cleaner): int
    {
        $minutes = $this->option('minutes');
        $minutes = is_numeric($minutes) ? (int) $minutes : (int) config('converter.cleanup_minutes');

        $removed = $cleaner->purge($minutes);

        $this->info("{$removed} 件の古い作業ディレクトリを削除しました。");

        return self::SUCCESS;
    }
}
