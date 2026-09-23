# kunpo-ali-aar 升级操作手册

本仓库用于向 JitPack 分发阿里一键登录（号码认证服务）的三个预编译 aar：

| artifactId | 当前版本 | 源文件名示例 |
|---|---|---|
| auth_number_product | 2.14.24 | auth_number_product-2.14.24-log-online-standard-cuum-release.aar |
| logger | 2.2.2 | logger-2.2.2-release.aar |
| main | 2.2.3 | main-2.2.3-release.aar |

对外**聚合坐标**（消费端一行拉三个 aar，各自保持源版本号）：

```gradle
api 'com.github.kaission2.kunpo-ali-aar:kunpo_ali_auth_number:2.14.24'
```

---

## 一、涉及的三方

1. **GitHub 仓库** `kaission2/kunpo-ali-aar`：存放 aar 文件、jitpack.yml、kunpo-ali-bundle.pom（聚合 pom）、pom.xml，并按版本打 tag。
2. **JitPack**：按 tag 构建，把构件发布到 `https://jitpack.io/com/github/kaission2/kunpo-ali-aar/...`。
3. **消费端**：`KunpoSDK/build.gradle` 里的一行聚合坐标。

> 说明：本机到 github.com 的 git 端口不通，因此所有 GitHub 操作走 REST API（api.github.com 可达），升级脚本不需要也不应该使用 git push。

---

## 二、升级前准备（一次性，可复用）

1. **GitHub fine-grained PAT**（建议每次升级现建、用完撤销）：
   - Repository access：**All repositories**
   - Repository permissions：**Administration**（读写）、**Contents**（读写）
2. **JitPack authToken**（长期有效，妥善保管）：
   - 登录 https://jitpack.io → 打开 https://jitpack.io/w/user → 页面上 `jp_...` 开头的 **authToken**
3. **三个新 aar 文件**，放在本地任意目录，**文件名必须含版本号**（脚本靠文件名提取版本）：
   - `xxx-X.Y.Z-xxx.aar` 格式，例如 `logger-2.2.3-release.aar`

---

## 三、升级步骤（一键脚本）

升级脚本位于本仓库根目录 `upgrade_kunpo_ali.py`。

### 第 1 步：放置三个新 aar

把三个新 aar 放到本地目录（如 `KunpoSDK/libs/`），确认文件名含版本号。

### 第 2 步：执行升级脚本

```bash
python3 upgrade_kunpo_ali.py \
    --pat <github_pat> \
    --jitpack-token <jitpack_authToken> \
    --auth <auth_aar路径> \
    --logger <logger_aar路径> \
    --main <main_aar路径>
```

### 第 3 步：脚本自动完成（无需人工干预）

1. 从文件名提取三个版本号（auth 版本 = 对外 tag 版本）；
2. 上传三个 aar 到 GitHub 仓库 `aar/` 目录（Contents API）；
3. 写 `jitpack.yml`：三个 aar 各自源版本 install + 聚合 pom install；
4. 写 `kunpo-ali-bundle.pom`：**版本等于 tag 的依赖写死；不等于 tag 的用属性占位**（绕开 JitPack 的 pom 版本重写）；
5. 写根 `pom.xml`（version = auth 版本）；
6. 重建三个 tag（auth 版本 / logger 版本 / main 版本）指向新 commit；
7. 用 JitPack token：DELETE 三个 tag 的旧构建缓存 → 请求构件触发新构建 → 轮询 → 验证 URL。

### 第 4 步：改 KunpoSDK 依赖

按脚本末尾打印的提示，把 `KunpoSDK/build.gradle` 里的一行改为新版本：

```gradle
api 'com.github.kaission2.kunpo-ali-aar:kunpo_ali_auth_number:<新auth版本>'
```

### 第 5 步：编译验证

```bash
./gradlew :app:assembleDebug
```

看到 BUILD SUCCESSFUL 即完成。

### 第 6 步：撤销 GitHub PAT

去 GitHub 设置 → Developer settings 撤销本次使用的 PAT。

---

## 四、实操举例：升级到 2.14.25 / 2.2.3 / 2.2.4

假设拿到三个新文件并放在 `/tmp/new-aar/`：

```
/tmp/new-aar/auth_number_product-2.14.25-log-online-standard-cuum-release.aar
/tmp/new-aar/logger-2.2.3-release.aar
/tmp/new-aar/main-2.2.4-release.aar
```

### 步骤 1：新建 GitHub PAT

GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token：
- Repository access：All repositories
- Permissions：Administration（Read and write）、Contents（Read and write）
- 复制生成的 `github_pat_...`（本次示例用 `<GHPAT>` 占位）

### 步骤 2：执行升级命令

```bash
python3 upgrade_kunpo_ali.py \
    --pat <GHPAT> \
    --jitpack-token <JITPACK_TOKEN> \
    --auth /tmp/new-aar/auth_number_product-2.14.25-log-online-standard-cuum-release.aar \
    --logger /tmp/new-aar/logger-2.2.3-release.aar \
    --main /tmp/new-aar/main-2.2.4-release.aar
```

脚本输出示意：

```
版本: auth=2.14.25 logger=2.2.3 main=2.2.4（对外 tag = 2.14.25）
1) 上传 aar 文件
  ok  aar/auth_number_product-2.14.25-log-online-standard-cuum-release.aar
  ok  aar/logger-2.2.3-release.aar
  ok  aar/main-2.2.4-release.aar
2) 写 jitpack.yml
3) 写 kunpo-ali-bundle.pom（属性占位绕 JitPack 重写）
4) 写 pom.xml
5) 重建 tag
  ok  tag 2.14.25 -> ab12cd34ef56
  ok  tag 2.2.3 -> ab12cd34ef56
  ok  tag 2.2.4 -> ab12cd34ef56
6) JitPack 删除旧构建 + 触发新构建
  ...
JitPack 结果: 全部 ok
```

### 步骤 3：改 KunpoSDK 依赖（改动前后对比）

改动前：

```gradle
api 'com.github.kaission2.kunpo-ali-aar:kunpo_ali_auth_number:2.14.24'
```

改动后：

```gradle
api 'com.github.kaission2.kunpo-ali-aar:kunpo_ali_auth_number:2.14.25'
```

### 步骤 4：编译验证

```bash
./gradlew :app:assembleDebug
```

构建成功后，Gradle 会拉下三个 aar，版本分别为 2.14.25 / 2.2.3 / 2.2.4。

### 步骤 5：撤销 PAT

GitHub 设置里 Revoke 掉 `<GHPAT>`。

---

## 五、不跑脚本的手动步骤（备查）

### 1. GitHub 端（走 API 或 git）

1. 上传三个新 aar 到 `aar/` 目录；
2. 改 `jitpack.yml`：三行 install-file 的 `-Dfile` 文件名和 `-Dversion` 改成新版本；
3. 改 `kunpo-ali-bundle.pom`：
   - 依赖版本 == 新 tag 版本 → 写死；
   - 依赖版本 != 新 tag 版本 → 放 properties + `${...}` 引用；
4. 改根 `pom.xml` 的 `<version>`；
5. 打三个 tag（auth 版本 / logger 版本 / main 版本）指向最新 commit。

### 2. JitPack 端

1. 有旧构建缓存的 tag，先删：
   ```bash
   curl -u <authToken>: -X DELETE https://jitpack.io/api/builds/com.github.kaission2.kunpo-ali-aar/<tag>
   ```
2. 请求构件 URL 触发构建（三个都要触发）：
   ```bash
   curl -o /dev/null "https://jitpack.io/com/github/kaission2/kunpo-ali-aar/<artifactId>/<版本>/<artifactId>-<版本>.pom"
   ```
3. 轮询 `https://jitpack.io/api/builds/com.github.kaission2.kunpo-ali-aar/<tag>` 直到 status=ok 且 commit 为最新；
4. 验证聚合 pom 与三个 aar 的 pom/aar URL 全部 200。

### 3. 消费端

1. 改 KunpoSDK 的一行坐标；
2. 只有**同一坐标内容重发过**（版本号不变但内容变了）才需要清 Gradle 缓存：
   ```bash
   rm -rf ~/.gradle/caches/modules-2/files-2.1/com.github.kaission2.kunpo-ali-aar \
          ~/.gradle/caches/modules-2/metadata-*/descriptors/com.github.kaission2.kunpo-ali-aar
   ```
   全新版本号不需要清缓存。

---

## 六、四个必踩的坑

1. **JitPack 会重写 pom 依赖版本为 tag 版本**：聚合 pom 里与 tag 版本不同的依赖必须用属性占位（`<logger.v>2.2.3</logger.v>` + `<version>${logger.v}</version>`），且属性值等于 tag 版本的属性会被 JitPack 删除定义——所以等于 tag 的直接写死。
2. **JitPack 按 tag 缓存构建**：同 tag 名重建后必须 DELETE 旧构建（`curl -u <token>: -X DELETE .../api/builds/.../<tag>`），否则永远拿到旧记录；DELETE 后第一次请求构件 URL 即触发新构建。
3. **JitPack 只发布版本 == tag 的构件**：logger / main 的版本与 auth 版本不同，必须在各自版本名的 tag 上构建才会发布（所以每次升级要打三个 tag）。
4. **Gradle 缓存固定版本 pom**：同一坐标重发内容后，需删除 `files-2.1` 与 `metadata-*/descriptors` 下对应 group 目录，新 pom 内容才会生效。

---

## 七、安全提醒

- GitHub PAT 用一次撤销一次，不要长期保留或写进任何提交；
- JitPack authToken 具有删构建权限，不要泄露；
- 升级脚本 `upgrade_kunpo_ali.py` 本身不含任何令牌，令牌只通过命令行参数传入。
