#!/usr/bin/env python3
"""Build an offline component-state preview from a Visual PRD UI profile."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from ui_profile import load_ui_profile, profile_css


def build(profile_path: Path, output: Path) -> None:
    profile = load_ui_profile(profile_path)
    components = profile["components"]
    name = html.escape(profile["name"])
    profile_json = json.dumps(profile, ensure_ascii=False).replace("</", "<\\/")
    page = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} · 组件预览</title><style>
{profile_css(profile)}
*{{box-sizing:border-box}}[hidden]{{display:none!important}}body{{margin:0;padding:var(--space-page);color:var(--ink);background:var(--canvas);font:var(--font-size)/var(--line-height) var(--font-family)}}
main{{max-width:1080px;margin:auto}}h1{{margin:0 0 6px}}h2{{margin:0 0 14px;font-size:18px}}p{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}}.panel{{padding:var(--space-panel);border:1px solid var(--line);border-radius:var(--radius-panel);background:var(--surface);box-shadow:var(--panel-shadow)}}
button,input,select{{font:inherit}}button,.control,.field input,.field select{{padding:var(--control-y) var(--control-x);border:1px solid var(--line);border-radius:var(--radius-control);background:var(--surface);color:var(--ink)}}button{{cursor:pointer}}button.primary{{border-color:var(--brand);background:var(--brand);color:var(--brand-contrast)}}button.danger{{border-color:var(--danger);color:var(--danger)}}button:disabled{{cursor:not-allowed;opacity:.45}}button:focus-visible,input:focus-visible{{outline:3px solid color-mix(in srgb,var(--focus) 30%,transparent);outline-offset:2px}}.row{{display:flex;flex-wrap:wrap;gap:var(--gap);align-items:center}}
.segmented,.tabs,.tabs-segmented{{display:inline-flex;gap:4px;padding:4px;border:1px solid var(--line);border-radius:var(--radius-control)}}.segmented .active,.tabs .active,.tabs-segmented .active{{border-color:var(--brand);background:var(--brand);color:var(--brand-contrast)}}.chips button,.tabs-pills button{{border-radius:999px}}.chips .active{{border-color:var(--brand);color:var(--brand)}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left}}th{{background:color-mix(in srgb,var(--canvas) 75%,var(--surface));color:var(--muted)}}.density-compact th,.density-compact td{{padding:7px 9px}}.field{{display:grid;gap:5px}}.field.error input{{border-color:var(--danger)}}.error-text{{color:var(--danger);font-size:12px}}.modal{{max-width:460px;padding:var(--space-panel);border-radius:var(--radius-overlay);background:var(--surface);box-shadow:var(--overlay-shadow)}}.empty{{padding:28px;text-align:center;border:1px dashed var(--line);border-radius:var(--radius-panel)}}.list-cards{{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--gap)}}.list-card{{padding:14px;border:1px solid var(--line);border-radius:var(--radius-panel)}}.density-compact .list-card{{padding:10px}}.editor{{margin:18px 0}}.editor-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}.actions{{display:flex;justify-content:flex-end;margin-top:12px}}
@media(max-width:640px){{body{{padding:14px}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<p>界面规范预览</p><h1>{name}</h1><p id="profile-summary"></p>
<section class="panel editor"><h2>实时切换</h2><div class="editor-grid">
<label class="field"><span>筛选器</span><select data-profile-path="components.filter.variant"><option value="select">下拉</option><option value="segmented">分段</option><option value="chips">标签</option></select></label>
<label class="field"><span>列表</span><select data-profile-path="components.list.variant"><option value="table">表格</option><option value="cards">卡片</option></select></label>
<label class="field"><span>列表密度</span><select data-profile-path="components.list.density"><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label>
<label class="field"><span>Tab</span><select data-profile-path="components.tabs.variant"><option value="underline">下划线</option><option value="pills">胶囊</option><option value="segmented">分段</option></select></label>
<label class="field"><span>品牌色</span><input type="color" data-profile-path="tokens.colors.brand"></label>
</div><div class="actions"><button id="export-profile" class="primary" type="button">导出 ui-profile.json</button></div></section>
<div class="grid">
<section class="panel"><h2>按钮状态</h2><div class="row"><button class="primary">主要操作</button><button>次要操作</button><button class="danger">危险操作</button><button disabled>禁用状态</button><button aria-busy="true">处理中…</button></div></section>
<section class="panel"><h2>筛选与选中</h2><div id="filter-preview" class="row"><button class="active">全部</button><button>进行中</button><button>已完成</button></div></section>
<section class="panel"><h2>Tab 状态</h2><div id="tabs-preview" class="tabs"><button class="active">概览</button><button>关键结果</button><button>动态</button></div></section>
<section class="panel"><h2>表单状态</h2><label class="field"><span>默认字段</span><input value="示例内容"></label><br><label class="field error"><span>错误字段</span><input aria-invalid="true" value=""><span class="error-text">此字段为必填项</span></label></section>
<section class="panel"><h2>列表</h2><div id="table-preview"><table><thead><tr><th>目标</th><th>负责人</th><th>状态</th></tr></thead><tbody><tr><td>提升交付质量</td><td>成员甲</td><td>进行中</td></tr><tr><td>完善评审流程</td><td>成员乙</td><td>已完成</td></tr></tbody></table></div><div id="cards-preview" class="list-cards" hidden><article class="list-card"><strong>提升交付质量</strong><p>成员甲 · 进行中</p></article><article class="list-card"><strong>完善评审流程</strong><p>成员乙 · 已完成</p></article></div></section>
<section class="panel"><h2>空状态</h2><div class="empty"><strong>暂无数据</strong><p>调整筛选条件或创建第一条记录。</p></div></section>
<section class="panel"><h2>弹层</h2><div class="modal"><h3>编辑内容</h3><p>检查弹层圆角、阴影、按钮和字段状态。</p><div class="row"><button>取消</button><button class="primary">保存</button></div></div></section>
</div></main><script>
const profile={profile_json};
const read=path=>path.split('.').reduce((value,key)=>value[key],profile);
const write=(path,value)=>{{const keys=path.split('.');let cursor=profile;keys.forEach((key,index)=>{{if(index===keys.length-1)cursor[key]=value;else cursor=cursor[key];}});}};
function apply(){{const filter=profile.components.filter.variant;const list=profile.components.list.variant;const density=profile.components.list.density;const tabs=profile.components.tabs.variant;document.documentElement.style.setProperty('--brand',profile.tokens.colors.brand);document.querySelector('#filter-preview').className=`row ${{filter}}`;document.querySelector('#tabs-preview').className=`tabs tabs-${{tabs}}`;document.querySelector('#table-preview').hidden=list==='cards';document.querySelector('#cards-preview').hidden=list!=='cards';document.querySelector('#table-preview').className=`density-${{density}}`;document.querySelector('#cards-preview').className=`list-cards density-${{density}}`;document.querySelector('#profile-summary').textContent=`筛选：${{filter}} · 列表：${{list}} · 密度：${{density}} · Tab：${{tabs}}`;}}
document.querySelectorAll('[data-profile-path]').forEach(field=>{{field.value=read(field.dataset.profilePath);field.addEventListener('input',()=>{{write(field.dataset.profilePath,field.value);apply();}});}});
document.querySelector('#export-profile').addEventListener('click',()=>{{const blob=new Blob([JSON.stringify(profile,null,2)+'\\n'],{{type:'application/json'}});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='ui-profile.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0);}});
apply();
</script></body></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成界面规范离线预览")
    parser.add_argument("profile", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.profile, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PASS: 已生成 {args.output}")


if __name__ == "__main__":
    main()
