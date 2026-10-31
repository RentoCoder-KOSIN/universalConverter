import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from converter.main import convert

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def run(command):
    return subprocess.run(command, capture_output=True, check=True, timeout=60)


def probe(path):
    result = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(result.stdout)


def video_stream(path):
    return next(s for s in probe(path)["streams"] if s["codec_type"] == "video")


def audio_stream(path):
    return next((s for s in probe(path)["streams"] if s["codec_type"] == "audio"), None)


@unittest.skipIf(FFMPEG is None or FFPROBE is None, "FFmpeg / ffprobe が入っていないためスキップ")
class VideoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.fixtures = Path(cls._tmp.name)

        # 音声付き MP4（160x120, 1 秒）
        cls.mp4 = cls.fixtures / "clip.mp4"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.mp4)])

        # 音声なし MP4
        cls.silent_mp4 = cls.fixtures / "silent.mp4"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(cls.silent_mp4)])

        # 大きめ（1280x960）の WebM
        cls.big_webm = cls.fixtures / "big.webm"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x960:rate=5:duration=1",
             "-c:v", "libvpx", "-b:v", "500k", "-deadline", "realtime", "-cpu-used", "8", str(cls.big_webm)])

        # 幅・高さが奇数の WebM（161x121）
        cls.odd_webm = cls.fixtures / "odd.webm"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=161x121:rate=10:duration=1",
             "-c:v", "libvpx", "-b:v", "300k", "-deadline", "realtime", "-cpu-used", "8", str(cls.odd_webm)])

        # 音声だけの M4A
        cls.m4a = cls.fixtures / "tone.m4a"
        run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:a", "aac", str(cls.m4a)])

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.work = Path(self._work.name)

    def tearDown(self):
        self._work.cleanup()

    def convert(self, op, src, name):
        out = self.work / name
        convert(op, src, out)
        return out

    def copy_as(self, src, name):
        dest = self.work / name
        shutil.copy(src, dest)
        return dest

    # ---- 正常系 ----

    def test_mp4_to_mp4_is_h264_with_audio(self):
        out = self.convert("video_to_mp4", self.mp4, "o.mp4")
        self.assertEqual(video_stream(out)["codec_name"], "h264")
        self.assertEqual(audio_stream(out)["codec_name"], "aac")

    def test_mp4_to_webm_is_vp9_and_opus(self):
        out = self.convert("video_to_webm", self.mp4, "o.webm")
        self.assertEqual(video_stream(out)["codec_name"], "vp9")
        self.assertEqual(audio_stream(out)["codec_name"], "opus")

    def test_webm_to_mp4(self):
        out = self.convert("video_to_mp4", self.big_webm, "o.mp4")
        self.assertEqual(video_stream(out)["codec_name"], "h264")

    def test_video_without_audio_is_converted_without_audio(self):
        out = self.convert("video_to_mp4", self.silent_mp4, "o.mp4")
        self.assertIsNone(audio_stream(out))

    def test_odd_dimensions_are_made_even(self):
        for op, name in [("video_to_mp4", "o.mp4"), ("video_to_webm", "o.webm"), ("video_to_mp4_small", "s.mp4")]:
            with self.subTest(op=op):
                stream = video_stream(self.convert(op, self.odd_webm, name))
                self.assertEqual(stream["width"] % 2, 0)
                self.assertEqual(stream["height"] % 2, 0)

    def test_small_scales_down_to_720(self):
        out = self.convert("video_to_mp4_small", self.big_webm, "o.mp4")
        stream = video_stream(out)
        self.assertEqual(stream["height"], 720)
        self.assertEqual(stream["width"], 960)

    def test_small_does_not_upscale(self):
        stream = video_stream(self.convert("video_to_mp4_small", self.mp4, "o.mp4"))
        self.assertEqual((stream["width"], stream["height"]), (160, 120))

    def test_extract_audio_makes_mp3(self):
        out = self.convert("video_extract_audio", self.mp4, "o.mp3")
        self.assertEqual(audio_stream(out)["codec_name"], "mp3")
        self.assertIsNone(next((s for s in probe(out)["streams"] if s["codec_type"] == "video"), None))

    def test_metadata_is_not_copied(self):
        tagged = self.work / "tagged.mp4"
        run([FFMPEG, "-v", "error", "-i", str(self.mp4), "-c", "copy",
             "-metadata", "title=SecretTitle", "-metadata", "location=+34.0+135.0/", str(tagged)])
        out = self.convert("video_to_mp4", tagged, "o.mp4")
        tags = probe(out)["format"].get("tags", {})
        self.assertNotIn("SecretTitle", json.dumps(tags))
        self.assertNotIn("location", tags)

    # ---- 異常系 ----

    def test_no_audio_track_for_extraction(self):
        with self.assertRaises(ValueError) as ctx:
            self.convert("video_extract_audio", self.silent_mp4, "o.mp3")
        self.assertIn("音声", str(ctx.exception))

    def test_audio_only_file_is_rejected_as_video(self):
        for op, name in [("video_to_mp4", "o.mp4"), ("video_to_webm", "o.webm")]:
            with self.subTest(op=op):
                with self.assertRaises(ValueError) as ctx:
                    self.convert(op, self.m4a, name)
                self.assertIn("映像", str(ctx.exception))

    def test_text_garbage_and_empty_files_are_rejected(self):
        for name, data in [("text.mp4", "これは動画ではありません".encode()), ("empty.mp4", b""),
                           ("junk.webm", os.urandom(2048))]:
            with self.subTest(file=name):
                src = self.work / name
                src.write_bytes(data)
                with self.assertRaises(ValueError):
                    convert("video_to_mp4", src, self.work / "o.mp4")

    def test_playlists_that_reference_other_files_are_rejected(self):
        secret = self.work / "secret.txt"
        secret.write_text("TOP-SECRET")
        cases = {
            "hls.mp4": f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile://{secret}\n#EXT-X-ENDLIST\n",
            "concat.mp4": f"ffconcat version 1.0\nfile '{secret}'\n",
            "sdp.webm": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=x\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio 5004 RTP/AVP 0\r\n",
        }
        for name, text in cases.items():
            with self.subTest(file=name):
                src = self.work / name
                src.write_text(text)
                out = self.work / "o.mp4"
                with self.assertRaises(ValueError) as ctx:
                    convert("video_to_mp4", src, out)
                self.assertNotIn("TOP-SECRET", str(ctx.exception))
                self.assertFalse(out.exists())

    def test_truncated_video_is_rejected(self):
        src = self.work / "cut.mp4"
        src.write_bytes(self.mp4.read_bytes()[:300])
        with self.assertRaises(ValueError):
            convert("video_to_mp4", src, self.work / "o.mp4")

    def test_too_long_video_is_rejected(self):
        from converter.formats import video as module
        with mock.patch.object(module, "MAX_DURATION_SECONDS", 0.5):
            with self.assertRaises(ValueError) as ctx:
                convert("video_to_mp4", self.mp4, self.work / "o.mp4")
        self.assertIn("長すぎ", str(ctx.exception))

    def test_too_large_resolution_is_rejected(self):
        from converter.formats import video as module
        with mock.patch.object(module, "MAX_FRAME_PIXELS", 10_000):
            with self.assertRaises(ValueError) as ctx:
                convert("video_to_mp4", self.mp4, self.work / "o.mp4")
        self.assertIn("解像度", str(ctx.exception))

    def test_output_size_limit_removes_the_output(self):
        from converter.formats import video as module
        out = self.work / "o.mp4"
        with mock.patch.object(module, "MAX_OUTPUT_BYTES", 1000):
            with self.assertRaises(ValueError) as ctx:
                convert("video_to_mp4", self.mp4, out)
        self.assertIn("大きすぎ", str(ctx.exception))
        self.assertFalse(out.exists())

    def test_timeout_is_reported_as_invalid_input(self):
        with mock.patch.dict(os.environ, {"CONVERTER_FFMPEG_TIMEOUT": "0.001"}):
            with self.assertRaises(ValueError) as ctx:
                convert("video_to_mp4", self.mp4, self.work / "o.mp4")
        self.assertIn("時間", str(ctx.exception))

    def test_missing_ffmpeg_raises_import_error(self):
        for variable in ("CONVERTER_FFMPEG", "CONVERTER_FFPROBE"):
            with self.subTest(variable=variable):
                with mock.patch.dict(os.environ, {variable: "/nonexistent/tool"}):
                    with self.assertRaises(ImportError):
                        convert("video_to_mp4", self.mp4, self.work / "o.mp4")

    def test_error_messages_do_not_contain_paths(self):
        src = self.work / "junk.mp4"
        src.write_bytes(os.urandom(2048))
        with self.assertRaises(ValueError) as ctx:
            convert("video_to_mp4", src, self.work / "o.mp4")
        self.assertNotIn(str(self.work), str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
