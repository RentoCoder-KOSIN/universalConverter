<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Route;
use Tests\TestCase;

class SiteDesignTest extends TestCase
{
    public function test_home_page_lists_every_group_and_links_to_the_converter(): void
    {
        $response = $this->get('/')->assertOk();

        $groups = collect(config('converter.operations'))->pluck('group')->unique();

        foreach ($groups as $group) {
            $response->assertSee($group);
        }

        $response->assertSee('変換をはじめる');
        $response->assertSee(route('converter.index'));
    }

    public function test_pages_link_the_stylesheet_and_it_exists(): void
    {
        $this->assertFileExists(public_path('css/site.css'));

        $this->get('/')->assertSee('css/site.css');
        $this->get('/converter')->assertSee('css/site.css');
    }

    public function test_converter_form_keeps_the_previous_choice_after_an_error(): void
    {
        $html = $this->withSession(['_old_input' => ['operation' => 'audio_to_wav']])
            ->get('/converter')
            ->assertOk()
            ->getContent();

        $this->assertMatchesRegularExpression(
            '/<input type="radio" name="operation" value="audio_to_wav"[^>]*\schecked[\s>]/s',
            $html,
        );
        $this->assertDoesNotMatchRegularExpression(
            '/<input type="radio" name="operation" value="csv_to_json"[^>]*\schecked[\s>]/s',
            $html,
        );
    }

    public function test_converter_form_selects_the_first_operation_by_default(): void
    {
        $first = array_key_first(config('converter.operations'));

        $html = $this->get('/converter')->assertOk()->getContent();

        $this->assertMatchesRegularExpression(
            '/<input type="radio" name="operation" value="'.preg_quote($first, '/').'"[^>]*\schecked[\s>]/s',
            $html,
        );
    }

    public function test_removed_admin_and_item_pages_are_gone(): void
    {
        foreach (['/admin', '/admin/add', '/admin/edit/1', '/item', '/item/add', '/item/edit/1'] as $path) {
            $this->get($path)->assertNotFound();
        }

        $this->post('/admin/add')->assertNotFound();
        $this->post('/item/delete/1')->assertNotFound();
    }

    public function test_unknown_page_shows_the_designed_404(): void
    {
        $this->get('/no-such-page')
            ->assertNotFound()
            ->assertSee('ページが見つかりません')
            ->assertSee('変換の画面へ');
    }

    public function test_error_pages_explain_what_to_do(): void
    {
        Route::get('/_test/abort/{code}', fn (int $code) => abort($code));

        $expected = [
            403 => 'このページは開けません',
            404 => 'ページが見つかりません',
            413 => 'ファイルが大きすぎます',
            419 => '有効期限が切れました',
            429 => 'リクエストが多すぎます',
            500 => 'サーバーでエラーが起きました',
            503 => '利用できません',
            // 専用のページが無い番号は、4xx / 5xx 共通のページになる
            418 => 'リクエストを処理できません',
            502 => 'サーバーでエラーが起きました',
        ];

        foreach ($expected as $status => $text) {
            $this->get('/_test/abort/'.$status)
                ->assertStatus($status)
                ->assertSee($text)
                ->assertSee((string) $status)
                ->assertSee('変換の画面へ');
        }
    }

    public function test_error_pages_do_not_expose_internal_details(): void
    {
        Route::get('/_test/boom', fn () => abort(500, '/var/www/secret/path.php'));

        $this->get('/_test/boom')
            ->assertStatus(500)
            ->assertDontSee('/var/www/secret/path.php');
    }
}
