import{_ as e,c as i,o as s,a9 as t}from"./chunks/framework.C4_mTacX.js";const g=JSON.parse('{"title":"liteyuki.plugins.liteecho","description":"","frontmatter":{"title":"liteyuki.plugins.liteecho"},"headers":[],"relativePath":"en/dev/api/plugins/liteecho.md","filePath":"en/dev/api/plugins/liteecho.md","lastUpdated":1725101868000}'),a={name:"en/dev/api/plugins/liteecho.md"},n=t('<h1 id="liteyuki-plugins-liteecho" tabindex="-1">liteyuki.plugins.liteecho <a class="header-anchor" href="#liteyuki-plugins-liteecho" aria-label="Permalink to &quot;liteyuki.plugins.liteecho&quot;">​</a></h1><p>Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved</p><p>@Time : 2024/8/22 下午12:31 @Author : snowykami @Email : <a href="mailto:snowykami@outlook.com" target="_blank" rel="noreferrer">snowykami@outlook.com</a> @File : liteecho.py @Software: PyCharm</p><p><code>@on_startswith([&#39;liteecho&#39;], rule=is_su_rule).handle()</code></p><h3 id="async-func-liteecho-event-messageevent" tabindex="-1"><em><strong>async func</strong></em> <code>liteecho(event: MessageEvent)</code> <a class="header-anchor" href="#async-func-liteecho-event-messageevent" aria-label="Permalink to &quot;***async func*** `liteecho(event: MessageEvent)`&quot;">​</a></h3><details><summary><b>Source code</b> or <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/plugins/liteecho.py#L18" target="_blank">View on GitHub</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;">@on_startswith</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">([</span><span style="--shiki-light:#032F62;--shiki-dark:#9ECBFF;">&#39;liteecho&#39;</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">], </span><span style="--shiki-light:#E36209;--shiki-dark:#FFAB70;">rule</span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">is_su_rule)</span><span style="--shiki-light:#B31D28;--shiki-dark:#FDAEB7;--shiki-light-font-style:italic;--shiki-dark-font-style:italic;">.handle()</span></span>\n<span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">async</span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;"> def</span><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;"> liteecho</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(event: MessageEvent):</span></span>\n<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">    event.reply(event.raw_message.strip()[</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">8</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">:].strip())</span></span></code></pre></div></details>',6),l=[n];function h(o,p,r,c,k,d){return s(),i("div",null,l)}const y=e(a,[["render",h]]);export{g as __pageData,y as default};