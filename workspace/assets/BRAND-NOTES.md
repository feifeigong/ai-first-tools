# AI一手品牌资源

- `ai-first-logo.jpg` 是用户提供的原图，未修改。界面通过 WPF 在内存中展示横版品牌区域，不覆盖源文件。
- `ai-first-app-icon.png` 是内置图像工具基于原图提取的透明横版品牌资源，不再使用双行排版、白色底板或圆角外框；不替代原始品牌母版。
- `ai-first-logo.ico` 是透明 PNG 的 Windows 多尺寸格式打包，供程序、窗口和任务栏读取，不额外添加背景或边框。
- Windows 任务栏仍会给活动窗口绘制系统选中背景；它不是图标的一部分。

最终生成提示词：

> Use case: background-extraction. Edit target: supplied original AI一手 horizontal brand logo. This is NOT logo generation or redesign. Remove ONLY the white background and faint gray enclosing circle. Preserve the EXACT original horizontal single-line blue text 'AI一手', original letter/glyph shapes, relative letter spacing, original blue and lime underline, proportions and colors unchanged. Never arrange text on two rows. No tile, no rounded square, no border, no frame, no shadow, no decoration. Output actual transparent PNG on a square canvas, original horizontal mark centered as one intact lockup filling 94% of the canvas width, with transparent space above and below. White spaces inside letters must also be transparent. Crisp faithful extraction only, not reinterpretation. Intended use: borderless Windows app icon using the user's own original mark.

检查横版文字、透明背景和多尺寸编码后复制到项目资源目录。图像提取不是原始像素无损变换；原图仍是品牌母版，保持字节不变。

重建资源：`python build_brand.py assets/ai-first-logo.jpg --app-icon assets/ai-first-app-icon.png`。
