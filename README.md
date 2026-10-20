# open-trade-gateway-ci

The Kylin XC workflows build AMD64 and ARM64 gateway packages. Production and
evaluation modes share the same XC Trader API and are selected at runtime with
the upstream `is_production_mode` configuration.

## otg-go 麒麟 XC 发布

[`otg-go-arm64.yml`](.github/workflows/otg-go-arm64.yml) 和
[`otg-go-amd64-xc.yml`](.github/workflows/otg-go-amd64-xc.yml) 分别使用 GitHub 的
原生 ARM64 与 AMD64 runner，在固定摘要的对应架构麒麟 V10 镜像中构建 otg-go。
同一架构的生产和测评使用同一个 `kylin-xc` 软件包，模式由实例配置选择。

两个工作流共用 `run-otg-go-arm64-release` repository dispatch。上游
`shinnytech/otg-go` 的 `Unified release payload` 在 tag 推送、基础软件包发布
成功后发起一次请求，并等待两个工作流的最终结果。普通分支 push、PR 更新和
手动操作不会触发 XC 发布。

请求携带确定的源码 SHA、版本、上游运行 ID、重跑次数和唯一请求 ID。工作流核对
上游运行身份和 tag 指向，只构建对应提交。运行程序取自该版本，
目标机部署工具取自工作流固定的 `TOOLING_SHA`；重新封包后的 `source_commit`
同时记录两个提交。构建完成后核验文件摘要、ELF 架构及依赖，并在对应架构
runner 上生成测试实例包、执行其中的 `verify-extracted`，再到麒麟容器
执行启动检查，最后发布私有 OSS：

```text
oss://shinny-cd/otg-go/<版本>/dist/software/otg-go_<版本>_arm64_kylin-xc.tar.gz
oss://shinny-cd/otg-go/<版本>/dist/software/otg-go_<版本>_arm64_kylin-xc.tar.gz.sha256
oss://shinny-cd/otg-go/<版本>/dist/software/otg-go_<版本>_amd64_kylin-xc.tar.gz
oss://shinny-cd/otg-go/<版本>/dist/software/otg-go_<版本>_amd64_kylin-xc.tar.gz.sha256
```

不同内容不能覆盖已有版本。本公共仓库不上传含私有程序的 Actions 制品。
组包机使用上游 `make prepare-instance-deployment` 生成目标实例的 `.sh`。

接入顺序：先合并本仓库的工作流，再合并上游调用方。沿用仓库已有秘密：

- `KYLIN_CI`：读取私有 otg-go 源码、Git LFS 和麒麟 GHCR 镜像。
- `OSS_ACCESS_KEY`、`OSS_SECRET_KEY`：读取及写入上述 OSS 前缀；使用公网加速 endpoint。

上游仓库的 `KYLIN_CI` 另需向本仓库分发事件及读取 Actions 结果。
本仓库来源校验测试执行 `python3 tests/otg_go_xc_workflow_test.py`；
上游构建、组包及部署测试由上游仓库维护。
