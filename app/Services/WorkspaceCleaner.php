<?php

namespace App\Services;

use Illuminate\Support\Facades\File;

/**
 * 変換の作業ディレクトリ（storage/app/private/converter/<uuid>）の置き場と、古い残骸の削除。
 *
 * 通常はリクエストの終わりに削除される。ここで消すのは、プロセスの強制終了などで残ったもの。
 */
class WorkspaceCleaner
{
    public function root(): string
    {
        return storage_path('app/private/converter');
    }

    /**
     * 最終更新が $olderThanMinutes 分より前の作業ディレクトリを削除し、削除した数を返す。
     */
    public function purge(int $olderThanMinutes): int
    {
        if (! File::isDirectory($this->root())) {
            return 0;
        }

        $threshold = time() - max(1, $olderThanMinutes) * 60;
        $removed = 0;

        foreach (File::directories($this->root()) as $directory) {
            $modified = @filemtime($directory);

            if ($modified !== false && $modified < $threshold && File::deleteDirectory($directory)) {
                $removed++;
            }
        }

        return $removed;
    }
}
