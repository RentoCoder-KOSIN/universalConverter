@extends('errors.layout', [
    'code' => isset($exception) && method_exists($exception, 'getStatusCode') ? $exception->getStatusCode() : 500,
    'heading' => 'サーバーでエラーが起きました',
    'detail' => 'ファイルの内容ではなく、サーバー側の問題です。時間をおいてもう一度お試しください。続くときは管理者に連絡してください。',
])
