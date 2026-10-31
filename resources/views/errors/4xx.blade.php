@extends('errors.layout', [
    'code' => isset($exception) && method_exists($exception, 'getStatusCode') ? $exception->getStatusCode() : 400,
    'heading' => 'リクエストを処理できません',
    'detail' => '送られた内容に問題がありました。変換の画面を開き直して、もう一度お試しください。',
])
