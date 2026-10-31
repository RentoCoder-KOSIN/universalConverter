<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\Schema;

/**
 * 管理者・商品の画面（/admin /item）を削除したので、残っているテーブルを片づける。
 * テーブルが無い環境（新しく作った DB）では何もしない。
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::dropIfExists('admins');
        Schema::dropIfExists('items');
    }

    public function down(): void
    {
        // 削除した機能のテーブルなので、元には戻さない。
    }
};
