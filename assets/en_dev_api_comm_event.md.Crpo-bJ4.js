import{_ as e,c as s,o as a,a9 as t}from"./chunks/framework.C4_mTacX.js";const _=JSON.parse('{"title":"liteyuki.comm.event","description":"","frontmatter":{"title":"liteyuki.comm.event"},"headers":[],"relativePath":"en/dev/api/comm/event.md","filePath":"en/dev/api/comm/event.md","lastUpdated":1725101868000}'),i={name:"en/dev/api/comm/event.md"},n=t('<h1 id="module-liteyuki-comm-event" tabindex="-1"><strong>Module</strong> <code>liteyuki.comm.event</code> <a class="header-anchor" href="#module-liteyuki-comm-event" aria-label="Permalink to &quot;**Module** `liteyuki.comm.event`&quot;">​</a></h1><p>本模块用于轻雪主进程和子进程之间的通信的事件类</p><h3 id="class-event" tabindex="-1"><em><strong>class</strong></em> <code>Event</code> <a class="header-anchor" href="#class-event" aria-label="Permalink to &quot;***class*** `Event`&quot;">​</a></h3><hr><h4 id="func-init-self-name-str-data-dict-str-any" tabindex="-1"><em><strong>func</strong></em> <code>__init__(self, name: str, data: dict[str, Any])</code> <a class="header-anchor" href="#func-init-self-name-str-data-dict-str-any" aria-label="Permalink to &quot;***func*** `__init__(self, name: str, data: dict[str, Any])`&quot;">​</a></h4><details><summary><b>Source code</b> or <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/comm/event.py#L13" target="_blank">View on GitHub</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">def</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;"> __init__</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(self, name: </span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">str</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">, data: dict[</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">str</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">, Any]):</span></span>\n<span class="line"><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">    self</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">.name </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;"> name</span></span>\n<span class="line"><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">    self</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">.data </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;"> data</span></span></code></pre></div></details>',6),l=[n];function h(d,o,r,c,p,k){return a(),s("div",null,l)}const u=e(i,[["render",h]]);export{_ as __pageData,u as default};