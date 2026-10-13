# ppt-clone

**读取一个参考 PPT，复刻它的设计，生成一份新的、原生可编辑的 .pptx。**

```
reference.pptx ──extract-spec──▶ specs/<name>/ ──generate-pptx──▶ SVG ──convert──▶ .pptx
   （设计 DNA）                      （spec 规范）                 （逐页稿）     （原生形状）
```

不是"内容填模板"，而是先从参考稿里**提取设计规范**（真实 HEX 配色、字体、每页布局几何、可复用素材），再用这份规范生成新页面，最后导出成 PowerPoint 原生形状——文字、颜色、形状都能继续编辑。

## 环境

```bash
cd ~/.claude/skills/ppt-clone
./.venv/bin/python scripts/ppt_cli.py <command>     # 系统 python3 是 3.9，太旧
```

渲染预览用 LibreOffice（`soffice`）与 poppler（`pdftoppm`）。

## 命令

| 命令 | 作用 |
|------|------|
| `extract-spec <ref.pptx> [--name X]` | 读参考稿 → `specs/<X>/`（`spec.yaml` / `pages/` / `assets/`） |
| `generate-pptx --spec specs/X --outline outline.yaml -o out.pptx` | 按 spec 生成并导出（生成→评分→修复，≥90% 通过） |
| `convert <svg>... -o out.pptx` | SVG → 原生形状 PPTX |
| `list-specs` / `select-spec <name>` | 已提取的 spec / 设为默认 |
| `qa-balance <png-dir> --box L,T,R,B --deck-width W` | 量测每页留白均衡度（标记上挤下空 / 过疏页） |

## 快速上手

```bash
# 1. 提取参考稿的设计规范
./.venv/bin/python scripts/ppt_cli.py extract-spec 参考稿.pptx --name house

# 2. 准备内容大纲 outlines/content.yaml（title + body 列表），生成
./.venv/bin/python scripts/ppt_cli.py generate-pptx \
    --spec specs/house --outline outlines/content.yaml -o out.pptx

# 3. 或直接转换手写的 SVG
./.venv/bin/python scripts/ppt_cli.py convert build/*.svg -o out.pptx

# 4. 渲染后量测版面均衡
./.venv/bin/python scripts/ppt_cli.py qa-balance build/render \
    --box <L>,<T>,<R>,<B> --deck-width <deck 宽度>
```

## 关键原则

- **参考稿的背景/装饰在图版（slide layout）上**，只读 `slide.shapes` 会丢掉整页背景；提取时会一并读取 `slide_layout.shapes`。
- **配色解析成真实 HEX**：`accent1` 之类的 scheme 色、`lumMod/tint` 的深浅、`a:alpha` 透明度，python-pptx 的 `ColorFormat` 读不到，得读原始 XML。
- **SVG 文本不换行**：一行一个 `<text>`，中文断行交给 `ppt_clone.textfit.wrap_cjk`（不留悬挂括号、标点不起行、不留孤字）。
- **文字框必须不比字宽窄**，否则 LibreOffice/WPS 会自己重排。
- **纵向均衡**：字号自适应 + 余量给行距 + 整块居中（`layout_fit.fit_block`），别靠压缩行距硬塞。

## 结构

```
ppt-clone/
├── scripts/
│   ├── ppt_cli.py                 # CLI
│   └── ppt_clone/
│       ├── spec/                  # 提取：主题色/字体、元素、素材、页面分类
│       ├── converter/ finalize/   # SVG → DrawingML 原生形状
│       ├── ppt_generator.py slide_generator.py style_evaluator.py   # 生成 + 评分循环
│       ├── layout/designer.py     # 版面设计
│       └── textfit.py layout_fit.py layout_qa.py   # 中文断行 / 竖向适配 / 均衡验收
├── references/
│   ├── spec-format.md             # spec 结构
│   ├── prompt-ppt-layout.md       # 版面设计规则
│   └── lessons-learned.md         # 实战踩坑：症状 → 病因 → 解法（接手前先看）
└── tests/                         # ./.venv/bin/python -m pytest tests -q
```

## 依赖

Python 3.10+；`python-pptx` / `Pillow` / `PyYAML` / `lxml` / `pdf2image`；预览需要 LibreOffice + poppler。

## License

MIT
