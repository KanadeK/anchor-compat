# anchor-compat 中文说明

为已经发布的静态 HTML 页面和锚点建立兼容性基线。即使新版本的内部链接全都更新，旧的外部书签仍可能因标题改名失效；这个工具能发现这种回归。

需要 Python 3.11+，没有运行时第三方依赖。先按英文 README 安装，然后执行：

```sh
anchor-compat snapshot examples/old -o anchors.json
anchor-compat check examples/changed --baseline anchors.json
anchor-compat check examples/fixed --baseline anchors.json
```

前一次检查应失败并返回 1，后一次应成功并返回 0。PowerShell 用 `$LASTEXITCODE` 查看退出码。基线文件不会被覆盖。正式使用时把 `examples/old` 换成已发布版本的 HTML 构建目录，将基线加入版本控制，再检查新构建目录。

检查实际 HTML 的 `id` 和传统 `<a name>`，不用猜 Markdown 的标题生成规则。支持 JSON、重复锚点诊断、显式排除路径和逐地址退役声明。`pretty` URL 模式把 `index.html` 映射为目录路径；`file` 模式保留文件名。

仅适用于 UTF8 静态 HTML，不能证明浏览器跳转、JavaScript 动态锚点、内容语义或服务器重定向正确。模板内容不算有效目标；noscript 等依赖浏览器状态的内容须另外测试。限制与完整选项见 [英文 README](README.md)。卸载：`python -m pip uninstall anchor-compat`，并删除自己生成的基线文件。
