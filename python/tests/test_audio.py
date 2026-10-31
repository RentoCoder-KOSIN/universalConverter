import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from converter.formats import audio
from converter.main import convert

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _probe(path):
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


@unittest.skipIf(FFMPEG is None or FFPROBE is None, "FFmpeg が入っていないためスキップ")
class AudioConvertTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make_audio(self, name, seconds=1, rate=44100, channels=1, extra=()):
        """ffmpeg の正弦波ジェネレーターで音声ファイルを作る。"""
        path = self.tmp / name
        subprocess.run(
            [
                FFMPEG, "-v", "error", "-y",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate={rate}",
                "-ac", str(channels),
                *extra,
                str(path),
            ],
            check=True,
        )
        return path

    def run_convert(self, op, src, out_name):
        out = self.tmp / out_name
        convert(op, src, out)
        return out

    def codec_of(self, path):
        return _probe(path)["streams"][0]["codec_name"]

    def test_wav_to_each_format(self):
        src = self.make_audio("a.wav")
        for op, ext, codec in [
            ("audio_to_mp3", "mp3", "mp3"),
            ("audio_to_m4a", "m4a", "aac"),
            ("audio_to_flac", "flac", "flac"),
            ("audio_to_ogg", "ogg", "vorbis"),
            ("audio_to_wav", "wav", "pcm_s16le"),
        ]:
            with self.subTest(op=op):
                out = self.run_convert(op, src, f"o.{ext}")
                self.assertTrue(out.is_file())
                self.assertEqual(self.codec_of(out), codec)
                duration = float(_probe(out)["format"]["duration"])
                self.assertAlmostEqual(duration, 1.0, delta=0.3)

    def test_mp3_to_wav_is_real_wav(self):
        src = self.make_audio("a.mp3")
        out = self.run_convert("audio_to_wav", src, "o.wav")
        with wave.open(str(out)) as result:
            self.assertEqual(result.getnchannels(), 1)
            self.assertEqual(result.getsampwidth(), 2)

    def test_flac_to_mp3_and_back(self):
        src = self.make_audio("a.flac")
        mp3 = self.run_convert("audio_to_mp3", src, "o.mp3")
        flac = self.run_convert("audio_to_flac", mp3, "o.flac")
        self.assertEqual(self.codec_of(flac), "flac")

    def test_m4a_input(self):
        src = self.make_audio("a.m4a")
        out = self.run_convert("audio_to_mp3", src, "o.mp3")
        self.assertEqual(self.codec_of(out), "mp3")

    def test_input_extension_is_not_trusted(self):
        # 中身が WAV のファイルに .mp3 という名前を付けても、中身で判定して変換できる
        wav = self.make_audio("a.wav")
        disguised = self.tmp / "disguised.mp3"
        shutil.copy(wav, disguised)
        out = self.run_convert("audio_to_flac", disguised, "o.flac")
        self.assertEqual(self.codec_of(out), "flac")

    def test_stereo_is_kept_for_lossless_and_wav(self):
        src = self.make_audio("a.wav", channels=2)
        out = self.run_convert("audio_to_flac", src, "o.flac")
        self.assertEqual(_probe(out)["streams"][0]["channels"], 2)

    def test_surround_is_downmixed_for_mp3(self):
        # MP3 は 2ch までなので、5.1ch はステレオにダウンミックスされる
        src = self.make_audio("a.flac", channels=6)
        out = self.run_convert("audio_to_mp3", src, "o.mp3")
        self.assertEqual(_probe(out)["streams"][0]["channels"], 2)

    def test_surround_is_kept_for_flac(self):
        src = self.make_audio("a.flac", channels=6)
        out = self.run_convert("audio_to_flac", src, "o.flac")
        self.assertEqual(_probe(out)["streams"][0]["channels"], 6)

    def test_high_sample_rate_to_mp3(self):
        src = self.make_audio("a.flac", rate=96000)
        out = self.run_convert("audio_to_mp3", src, "o.mp3")
        self.assertEqual(self.codec_of(out), "mp3")

    def test_metadata_is_not_copied(self):
        src = self.make_audio("a.mp3", extra=("-metadata", "title=秘密のタイトル", "-metadata", "artist=誰か"))
        out = self.run_convert("audio_to_flac", src, "o.flac")
        tags = {k.lower(): v for k, v in _probe(out)["format"].get("tags", {}).items()}
        self.assertNotIn("title", tags)
        self.assertNotIn("artist", tags)

    def test_cover_art_is_dropped(self):
        # 映像（カバー画像）付きの MP3 でも音声だけが出力される
        src = self.make_audio("a.wav")
        cover = self.tmp / "cover.png"
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=16x16", "-frames:v", "1", str(cover)],
            check=True,
        )
        with_cover = self.tmp / "with_cover.mp3"
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-i", str(src), "-i", str(cover), "-map", "0:a", "-map", "1:v",
             "-c:a", "libmp3lame", "-c:v", "mjpeg", "-id3v2_version", "3", str(with_cover)],
            check=True,
        )
        out = self.run_convert("audio_to_flac", with_cover, "o.flac")
        types = [s["codec_type"] for s in _probe(out)["streams"]]
        self.assertEqual(types, ["audio"])

    def test_output_directory_is_created(self):
        src = self.make_audio("a.wav")
        out = self.tmp / "nested" / "dir" / "o.mp3"
        convert("audio_to_mp3", src, out)
        self.assertTrue(out.is_file())

    # ---- 異常系 ----

    def test_missing_input_raises(self):
        with self.assertRaises(FileNotFoundError):
            convert("audio_to_mp3", self.tmp / "none.mp3", self.tmp / "o.mp3")

    def test_empty_file_is_rejected(self):
        src = self.tmp / "empty.mp3"
        src.write_bytes(b"")
        with self.assertRaises(ValueError):
            convert("audio_to_wav", src, self.tmp / "o.wav")
        self.assertFalse((self.tmp / "o.wav").exists())

    def test_text_file_with_audio_extension_is_rejected(self):
        src = self.tmp / "fake.mp3"
        src.write_text("これは音声ではありません", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            convert("audio_to_wav", src, self.tmp / "o.wav")
        self.assertNotIn(str(self.tmp), str(caught.exception))

    def test_image_is_rejected(self):
        src = self.tmp / "pic.png"
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=16x16", "-frames:v", "1", str(src)],
            check=True,
        )
        with self.assertRaises(ValueError):
            convert("audio_to_mp3", src, self.tmp / "o.mp3")

    def test_truncated_audio_does_not_report_success_with_empty_output(self):
        src = self.make_audio("a.flac", seconds=2)
        data = src.read_bytes()
        broken = self.tmp / "broken.flac"
        broken.write_bytes(data[: len(data) // 2])
        out = self.tmp / "o.mp3"
        try:
            convert("audio_to_mp3", broken, out)
        except ValueError:
            self.assertFalse(out.exists())
        else:
            # 途中まで読めた場合は、空でない有効な MP3 になっていること
            self.assertGreater(out.stat().st_size, 0)

    def test_playlist_text_is_rejected(self):
        # HLS / concat 風のテキストでローカルファイルを読ませる攻撃を防ぐ
        secret = self.tmp / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        src = self.tmp / "list.mp3"
        src.write_text(f"ffconcat version 1.0\nfile '{secret}'\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            convert("audio_to_wav", src, self.tmp / "o.wav")

    def test_too_long_audio_is_rejected(self):
        src = self.make_audio("a.wav", seconds=3)
        with mock.patch.object(audio, "MAX_DURATION_SECONDS", 2):
            with self.assertRaises(ValueError) as caught:
                convert("audio_to_mp3", src, self.tmp / "o.mp3")
        self.assertIn("長すぎ", str(caught.exception))
        self.assertFalse((self.tmp / "o.mp3").exists())

    def test_too_large_output_is_rejected_and_removed(self):
        src = self.make_audio("a.wav", seconds=1)
        out = self.tmp / "o.wav"
        with mock.patch.object(audio, "MAX_OUTPUT_BYTES", 10_000):
            with self.assertRaises(ValueError) as caught:
                convert("audio_to_wav", src, out)
        self.assertIn("大きすぎ", str(caught.exception))
        self.assertFalse(out.exists())

    def test_unwritable_output_directory_fails(self):
        src = self.make_audio("a.wav")
        blocker = self.tmp / "blocker"
        blocker.write_text("file", encoding="utf-8")
        with self.assertRaises(OSError):
            convert("audio_to_mp3", src, blocker / "o.mp3")

    def test_timeout_is_reported_as_invalid_input(self):
        src = self.make_audio("a.wav")
        with mock.patch.dict(os.environ, {"CONVERTER_FFMPEG_TIMEOUT": "0.001"}):
            with self.assertRaises(ValueError) as caught:
                convert("audio_to_mp3", src, self.tmp / "o.mp3")
        self.assertIn("時間", str(caught.exception))

    def test_invalid_timeout_setting_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"CONVERTER_FFMPEG_TIMEOUT": "abc"}):
            self.assertEqual(audio._timeout(), float(audio.DEFAULT_TIMEOUT_SECONDS))


class AudioUnavailableTest(unittest.TestCase):
    """FFmpeg が無い環境では ImportError（= unavailable）になること。FFmpeg の有無に関わらず実行する。"""

    def test_missing_ffmpeg_raises_import_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.wav"
            src.write_bytes(b"RIFF")
            with mock.patch.dict(os.environ, {"CONVERTER_FFMPEG": "/nonexistent/ffmpeg"}):
                with self.assertRaises(ImportError):
                    convert("audio_to_mp3", src, Path(tmp) / "o.mp3")

    def test_cli_reports_unavailable_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.wav"
            src.write_bytes(b"RIFF")
            env = {**os.environ, "CONVERTER_FFMPEG": "/nonexistent/ffmpeg", "PYTHONPATH": "."}
            result = subprocess.run(
                [
                    "python3", "-m", "converter.main", "audio_to_mp3", str(src), str(Path(tmp) / "o.mp3"),
                ],
                capture_output=True,
                text=True,
                env=env,
                cwd=Path(__file__).resolve().parent.parent,
            )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "unavailable")
        self.assertNotIn("/nonexistent", payload["error"])


if __name__ == "__main__":
    unittest.main()
