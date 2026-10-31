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
