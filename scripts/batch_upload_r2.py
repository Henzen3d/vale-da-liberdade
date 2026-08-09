#!/usr/bin/env python3
"""
批量上传音频到 Cloudflare R2
扫描 public/audio/ 目录，上传缺失的文件
"""
import os
import sys
from pathlib import Path
import json
from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "web-jornal-liberdade")
R2_PUBLIC_DOMAIN = (os.getenv("R2_PUBLIC_DOMAIN") or "").rstrip("/")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_AUDIO = PROJECT_ROOT / "public" / "audio"
EPISODES_DIR = PROJECT_ROOT / "episodes"

def get_r2_client():
    import boto3
    from botocore.config import Config
    endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

def list_r2_objects(s3_client):
    """列出 R2 中已存在的对象"""
    try:
        resp = s3_client.list_objects_v2(Bucket=R2_BUCKET_NAME, MaxKeys=1000)
        return {obj["Key"] for obj in resp.get("Contents", [])}
    except Exception as e:
        print(f"❌ 无法列出 R2 对象: {e}")
        return set()

def upload_file(s3_client, local_path: Path, r2_key: str) -> bool:
    """上传单个文件到 R2"""
    try:
        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"  📤 上传: {local_path.name} ({size_mb:.2f} MB)")
        
        s3_client.upload_file(
            str(local_path),
            R2_BUCKET_NAME,
            r2_key,
            ExtraArgs={
                "ContentType": "audio/mpeg",
                "CacheControl": "public, max-age=31536000",
            }
        )
        
        # 创建 sidecar JSON
        date_str = local_path.stem  # 去掉 .mp3 后缀
        sidecar = {
            "date": date_str,
            "local_url": f"./audio/{local_path.name}",
            "r2_key": r2_key,
            "r2_url": f"{R2_PUBLIC_DOMAIN}/{r2_key}",
            "catalog_url": f"{R2_PUBLIC_DOMAIN}/{r2_key}",
            "r2_uploaded": True,
            "bytes": local_path.stat().st_size,
            "source": str(local_path),
        }
        sidecar_path = EPISODES_DIR / f"{date_str}-r2.json"
        sidecar_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
        
        print(f"  ✅ 完成: {R2_PUBLIC_DOMAIN}/{r2_key}")
        return True
    except Exception as e:
        print(f"  ❌ 失败 {local_path.name}: {e}")
        return False

def main():
    if not R2_ACCOUNT_ID or not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        print("❌ 错误: R2 凭证未配置")
        sys.exit(1)
    
    print(f"🔍 扫描目录: {PUBLIC_AUDIO}")
    print(f"☁️  Bucket: {R2_BUCKET_NAME}")
    print(f"🌐 域名: {R2_PUBLIC_DOMAIN}\n")
    
    s3 = get_r2_client()
    existing = list_r2_objects(s3)
    print(f"📦 R2 中已有 {len(existing)} 个对象\n")
    
    mp3_files = list(PUBLIC_AUDIO.glob("*.mp3"))
    print(f"🎵 找到 {len(mp3_files)} 个 MP3 文件\n")
    
    # 过滤出已存在的
    to_upload = []
    skipped = []
    for f in mp3_files:
        r2_key = f"audio/{f.name}"
        if r2_key in existing:
            skipped.append(f)
        else:
            to_upload.append(f)
    
    print(f"✅ 已上传: {len(skipped)} 个文件")
    print(f"📤 待上传: {len(to_upload)} 个文件\n")
    
    if not to_upload:
        print("🎉 所有文件已上传到 R2！")
        return 0
    
    # 开始上传
    success = 0
    fail = 0
    for i, f in enumerate(to_upload, 1):
        print(f"[{i}/{len(to_upload)}] ", end="")
        if upload_file(s3, f, f"audio/{f.name}"):
            success += 1
        else:
            fail += 1
    
    print(f"\n{'='*50}")
    print(f"📊 完成统计:")
    print(f"  ✅ 成功: {success}")
    print(f"  ❌ 失败: {fail}")
    print(f"  ⏭️ 跳过: {len(skipped)}")
    print(f"{'='*50}")
    
    return 0 if fail == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
