# vendor/

`jianying-editor-skill/` 拷贝自 [aavvcasdas/auto-catvideo](https://github.com/aavvcasdas/auto-catvideo) 里使用的
[jianying-editor-skill](https://github.com/luoluoluo22/jianying-editor-skill) v1.5.0（MIT，见其 LICENSE），
内含修改版 pyJianYingDraft。为了控制仓库体积，删掉了自带的大体积示例素材。

本仓库没有修改其中任何代码；草稿路径一致性、素材复制、元信息补全都在 `engine/draft_paths.py` 里，
在 skill 保存草稿之后进行，所以以后升级 skill 只需要整体替换这个文件夹。
