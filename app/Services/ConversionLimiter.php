<?php

namespace App\Services;

use App\Exceptions\ConversionException;
use Illuminate\Support\Facades\Cache;

/**
 * 同時に実行する変換の数を制限する。
 *
 * キャッシュのロックを「スロット」として数えるので、Web サーバーのプロセスが
 * 複数あっても上限が守られる（キャッシュは file / database / redis など、ロックに対応するもの）。
 * ロックには有効期限を付けるため、プロセスが異常終了してもスロットは自動で空く。
 */
class ConversionLimiter
{
    /**
     * @template T
     *
     * @param  callable(): T  $callback
     * @param  int|null  $timeout  この変換のタイムアウト秒（省略時は設定の timeout）。ロックの保持時間に使う
     * @return T
     *
     * @throws ConversionException 空きスロットが無いとき
     */
    public function run(callable $callback, ?int $timeout = null): mixed
    {
        $lock = $this->acquire($timeout);

        try {
            return $callback();
        } finally {
            $lock->release();
        }
    }

    private function acquire(?int $timeout): \Illuminate\Contracts\Cache\Lock
    {
        $slots = max(1, (int) config('converter.max_concurrent'));
        // 変換のタイムアウトより少し長く保持して、異常終了時だけ自動で解放されるようにする。
        $ttl = max(1, $timeout ?? (int) config('converter.timeout')) + 15;

        for ($slot = 0; $slot < $slots; $slot++) {
            $lock = Cache::lock('converter:slot:'.$slot, $ttl);

            if ($lock->get()) {
                return $lock;
            }
        }

        throw new ConversionException('現在、変換が混み合っています。しばらく待ってからもう一度お試しください。');
    }
}
