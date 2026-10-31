<?php

namespace App\Exceptions;

use RuntimeException;

/**
 * 変換に失敗したことを表す。
 * getMessage() は利用者にそのまま表示してよい文言だけを持つ（内部パスやスタックトレースを含めない）。
 */
class ConversionException extends RuntimeException
{
}
