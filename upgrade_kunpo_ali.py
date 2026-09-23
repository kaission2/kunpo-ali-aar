#!/usr/bin/env python3
"""
KunpoSDK 阿里一键登录 aar 一键升级发布脚本（GitHub + JitPack）

用法（在本仓库目录 kunpo-ali-aar/ 下）:
  python3 upgrade_kunpo_ali.py \\
      --pat <github_fine_grained_pat> \\
      --jitpack-token <jitpack_authToken(可选，跳过 JitPack 触发步骤时不传)> \\
      --auth aar/auth_number_product-2.14.25-log-online-standard-cuum-release.aar \\
      --logger aar/logger-2.2.3-release.aar \\
      --main aar/main-2.2.4-release.aar

脚本自动完成:
  1. 从文件名提取三个版本号（auth 的版本 = 对外 tag 版本）
  2. 上传三个 aar 到 GitHub 仓库 aar/ 目录
  3. 生成 jitpack.yml（三个 aar 各自源版本 install + 聚合 pom install）
  4. 生成 kunpo-ali-bundle.pom（== tag 的版本写死；!= tag 的版本用属性占位，躲开 JitPack 的 pom 版本重写）
  5. 根 pom.xml version = auth 版本
  6. 重建三个 tag（auth 版本 / logger 版本 / main 版本）指向新 commit
  7. [可选] 用 JitPack authToken: DELETE 三个 tag 的旧构建缓存 + 触发新构建 + 轮询 + 验证 URL

注意:
  - GitHub PAT 需要: 仓库 Administration + Contents 读写
  - JitPack authToken 在 https://jitpack.io/w/user 页面
  - 运行完请立即撤销/轮换 PAT
"""
import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request

USER = "kaission2"
REPO = "kunpo-ali-aar"
GROUP = f"com.github.{USER}.{REPO}"
API = "https://api.github.com"
JIT = "https://jitpack.io"
VER_RE = re.compile(r"-(\d+\.\d+\.\d+)-")


def gh(token, method, path, data=None):
    url = API + path
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Authorization", f"Bearer {token}")
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def http_get(url, auth=None):
    r = urllib.request.Request(url)
    if auth:
        r.add_header("Authorization", f"Basic {base64.b64encode((auth + ':').encode()).decode()}")
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def put_file(token, branch, path, content, message):
    """上传/更新单个文件，返回新 commit sha"""
    code, cur = gh(token, "GET", f"/repos/{USER}/{REPO}/contents/{path}?ref={branch}")
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if code == 200:
        payload["sha"] = cur["sha"]
    code, r = gh(token, "PUT", f"/repos/{USER}/{REPO}/contents/{path}", payload)
    if code not in (200, 201):
        sys.exit(f"上传 {path} 失败: {code} {r.get('message')}")
    print(f"  ok  {path}")
    return r["commit"]["sha"]


def set_tag(token, tag, commit_sha):
    gh(token, "DELETE", f"/repos/{USER}/{REPO}/git/refs/tags/{tag}")  # 不存在会 404，忽略
    code, r = gh(token, "POST", f"/repos/{USER}/{REPO}/git/refs",
                 {"ref": f"refs/tags/{tag}", "sha": commit_sha})
    if code != 201:
        sys.exit(f"tag {tag} 重建失败: {code} {r.get('message')}")
    print(f"  ok  tag {tag} -> {commit_sha[:12]}")


def build_pom(auth_v, logger_v, main_v):
    """聚合 pom：版本 == tag(auth_v) 的写死，!= tag 的用属性占位（JitPack 重写绕法）"""
    def dep(artifact, version):
        if version == auth_v:
            return (f"    <dependency>\n"
                    f"      <groupId>{GROUP}</groupId>\n"
                    f"      <artifactId>{artifact}</artifactId>\n"
                    f"      <version>{version}</version>\n"
                    f"      <type>aar</type>\n"
                    f"    </dependency>")
        prop = f"{artifact}.v"
        return (f"    <dependency>\n"
                f"      <groupId>{GROUP}</groupId>\n"
                f"      <artifactId>{artifact}</artifactId>\n"
                f"      <version>${{{prop}}}</version>\n"
                f"      <type>aar</type>\n"
                f"    </dependency>")

    props = []
    for artifact, version in (("logger", logger_v), ("main", main_v)):
        if version != auth_v:
            props.append(f"    <{artifact}.v>{version}</{artifact}.v>")
    props_xml = "\n".join(props)
    deps = "\n".join([
        dep("auth_number_product", auth_v),
        dep("logger", logger_v),
        dep("main", main_v),
    ])
    return (f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{GROUP}</groupId>
  <artifactId>kunpo_ali_auth_number</artifactId>
  <version>{auth_v}</version>
  <packaging>pom</packaging>
  <properties>
{props_xml}
  </properties>
  <dependencies>
{deps}
  </dependencies>
</project>
""")


def jitpack_rebuild(token, tag):
    """DELETE 旧构建（新 tag 不存在也安全）+ 触发构件请求 + 轮询"""
    code, _ = http_get(f"{JIT}/api/builds/{GROUP}/{tag}", auth=token)
    if code == 200:  # 存在旧构建记录 → 删除
        code, body = http_get(f"{JIT}/api/builds/{GROUP}/{tag}", auth=token)
        # DELETE 请求
        r = urllib.request.Request(f"{JIT}/api/builds/{GROUP}/{tag}", method="DELETE")
        r.add_header("Authorization", f"Basic {base64.b64encode((token + ':').encode()).decode()}")
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                print(f"  DELETE 旧构建 {tag}: {resp.read().decode()[:60]}")
        except urllib.error.HTTPError as e:
            print(f"  DELETE 旧构建 {tag}: {e.code} {e.read().decode()[:80]}")


def trigger_and_wait(token, artifact, version, expect_commit, wait_rounds=10):
    url = f"{JIT}/{GROUP}/{artifact}/{version}/{artifact}-{version}.pom"
    code, _ = http_get(url)
    print(f"  触发 {artifact}:{version} [{code}]")
    for i in range(wait_rounds):
        time.sleep(45)
        code, body = http_get(f"{JIT}/api/builds/{GROUP}/{version}", auth=token)
        try:
            d = json.loads(body)
            status, commit = d.get("status"), d.get("commit")
        except Exception:
            status, commit = None, None
        print(f"    轮{i + 1}: {status} {commit}")
        if status == "ok" and commit and commit.startswith(expect_commit[:12]):
            code, _ = http_get(url)
            print(f"    {artifact}:{version} pom [{code}]")
            return code == 200
        if status == "Error":
            return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pat", required=True, help="GitHub fine-grained PAT")
    ap.add_argument("--jitpack-token", default="", help="JitPack authToken（可选）")
    ap.add_argument("--auth", required=True, help="auth_number_product aar 路径")
    ap.add_argument("--logger", required=True, help="logger aar 路径")
    ap.add_argument("--main", required=True, help="main aar 路径")
    args = ap.parse_args()

    def ver_of(path):
        name = path.split("/")[-1]
        m = VER_RE.search(name)
        if not m:
            sys.exit(f"无法从文件名提取版本号: {name}（应为 xxx-X.Y.Z-xxx.aar）")
        return m.group(1)

    auth_v = ver_of(args.auth)
    logger_v = ver_of(args.logger)
    main_v = ver_of(args.main)
    print(f"版本: auth={auth_v} logger={logger_v} main={main_v}（对外 tag = {auth_v}）")

    code, repo = gh(args.pat, "GET", f"/repos/{USER}/{REPO}")
    if code != 200:
        sys.exit(f"GitHub 访问失败: {code}（检查 PAT）")
    branch = repo["default_branch"]
    print(f"默认分支: {branch}")

    # 1. 上传三个 aar
    print("1) 上传 aar 文件")
    commit_sha = None
    for path, artifact in ((args.auth, "auth_number_product"), (args.logger, "logger"), (args.main, "main")):
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        payload = {"message": f"upgrade {artifact}", "content": content, "branch": branch}
        code, cur = gh(args.pat, "GET", f"/repos/{USER}/{REPO}/contents/aar/{path.split('/')[-1]}?ref={branch}")
        if code == 200:
            payload["sha"] = cur["sha"]
        code, r = gh(args.pat, "PUT", f"/repos/{USER}/{REPO}/contents/aar/{path.split('/')[-1]}", payload)
        if code not in (200, 201):
            sys.exit(f"上传 aar 失败: {code} {r.get('message')}")
        commit_sha = r["commit"]["sha"]
        print(f"  ok  aar/{path.split('/')[-1]}")

    # 2. jitpack.yml
    print("2) 写 jitpack.yml")
    jitpack_yml = f"""jdk:
  - openjdk11
install:
  - mvn install:install-file -Dfile=aar/{args.auth.split('/')[-1]} -DgroupId={GROUP} -DartifactId=auth_number_product -Dversion={auth_v} -Dpackaging=aar -DgeneratePom=true
  - mvn install:install-file -Dfile=aar/{args.logger.split('/')[-1]} -DgroupId={GROUP} -DartifactId=logger -Dversion={logger_v} -Dpackaging=aar -DgeneratePom=true
  - mvn install:install-file -Dfile=aar/{args.main.split('/')[-1]} -DgroupId={GROUP} -DartifactId=main -Dversion={main_v} -Dpackaging=aar -DgeneratePom=true
  - mvn install:install-file -Dfile=kunpo-ali-bundle.pom -DgroupId={GROUP} -DartifactId=kunpo_ali_auth_number -Dversion={auth_v} -Dpackaging=pom
"""
    commit_sha = put_file(args.pat, branch, "jitpack.yml", jitpack_yml, f"upgrade to {auth_v}")

    # 3. 聚合 pom
    print("3) 写 kunpo-ali-bundle.pom（属性占位绕 JitPack 重写）")
    commit_sha = put_file(args.pat, branch, "kunpo-ali-bundle.pom",
                          build_pom(auth_v, logger_v, main_v), f"bundle pom {auth_v}")

    # 4. 根 pom.xml
    print("4) 写 pom.xml")
    pom_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>{GROUP}</groupId>
    <artifactId>kunpo-ali-aar</artifactId>
    <version>{auth_v}</version>
    <packaging>pom</packaging>
</project>
"""
    commit_sha = put_file(args.pat, branch, "pom.xml", pom_xml, f"pom.xml {auth_v}")

    # 5. 三个 tag 都指向新 commit（logger/main 的 tag 用于发布各自版本构件）
    print("5) 重建 tag")
    for tag in (auth_v, logger_v, main_v):
        set_tag(args.pat, tag, commit_sha)

    print(f"GitHub 端完成: tags {auth_v}/{logger_v}/{main_v} -> {commit_sha[:12]}")

    # 6. JitPack 触发
    if args.jitpack_token:
        print("6) JitPack 删除旧构建 + 触发新构建")
        ok = True
        for tag in (auth_v, logger_v, main_v):
            jitpack_rebuild(args.jitpack_token, tag)
        ok &= trigger_and_wait(args.jitpack_token, "kunpo_ali_auth_number", auth_v, commit_sha)
        ok &= trigger_and_wait(args.jitpack_token, "logger", logger_v, commit_sha)
        ok &= trigger_and_wait(args.jitpack_token, "main", main_v, commit_sha)
        print("JitPack 结果:", "全部 ok" if ok else "有失败，查 build.log")
    else:
        print("6) 跳过 JitPack 触发（未提供 --jitpack-token）；请到 https://jitpack.io/com/github/"
              f"{USER}/{REPO} 手动 Rebuild（登录后先删旧构建）")

    print()
    print("=" * 60)
    print("KunpoSDK 端操作:")
    print(f"  KunpoSDK/build.gradle 改为一行:")
    print(f"    api '{GROUP}:kunpo_ali_auth_number:{auth_v}'")
    print("  全新版本坐标无需清 Gradle 缓存；只有同一坐标内容重发过才需删除")
    print("  ~/.gradle/caches/modules-2/files-2.1 和 metadata-*/descriptors 下对应 group 目录")
    print("  验证: ./gradlew :app:assembleDebug")
    print("=" * 60)
    print("安全提醒: 请撤销本次使用的 GitHub PAT")


if __name__ == "__main__":
    main()
