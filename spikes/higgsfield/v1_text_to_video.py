"""V1 文字生影片：Seedance 2.5 text-to-video 的基本連通與耗時驗證。

用法：
  poetry run python v1_text_to_video.py          # 只估價
  poetry run python v1_text_to_video.py --yes    # 實際生成（產生費用）
"""

from hf_common import (
    OUTPUTS, T2V_MODEL, GenerationFailed, base_parser, download, load_credentials,
    make_client, quote, run_generation,
)

ARGS = {
    "prompt": "A cinematic scene at sunset",
    "duration": 5,
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "output_format": "mp4",
    "generate_audio": False,  # 架構書 §5.5：MVP 不生成音訊
}


def main() -> None:
    opts = base_parser(__doc__).parse_args()
    load_credentials()
    print("V1 文字生影片")
    [est] = quote([("V1 t2v 5s 720p 16:9", T2V_MODEL, ARGS)])
    if not opts.yes:
        print("只估價；加上 --yes 才會實際送出。")
        return
    try:
        rec = run_generation(make_client(), experiment="V1", label="t2v", model=T2V_MODEL,
                             arguments=ARGS, est=est)
    except GenerationFailed as e:
        raise SystemExit(str(e))
    path = download(rec["output_url"], OUTPUTS / "v1" / f"{rec['request_id']}.mp4")
    print(f"影片網址：{rec['output_url']}\n已下載：{path}")


if __name__ == "__main__":
    main()
