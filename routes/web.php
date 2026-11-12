<?php

use App\Http\Controllers\ConverterController;
use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return view('home', [
        'operations' => config('converter.operations'),
        'maxUploadKb' => config('converter.max_upload_kb'),
    ]);
});

Route::get('/converter', [ConverterController::class, 'index'])->name('converter.index');
Route::post('/converter', [ConverterController::class, 'convert'])->name('converter.convert');
Route::get('/converter/{taskId}', [ConverterController::class, 'status'])->name('converter.status');
Route::get('/converter/{taskId}/download', [ConverterController::class, 'download'])->name('converter.download');
