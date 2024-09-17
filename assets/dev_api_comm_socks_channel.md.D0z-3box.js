import{_ as s,c as a,o as i,a9 as e}from"./chunks/framework.C4_mTacX.js";const g=JSON.parse('{"title":"liteyuki.comm.socks_channel","description":"","frontmatter":{"title":"liteyuki.comm.socks_channel"},"headers":[],"relativePath":"dev/api/comm/socks_channel.md","filePath":"zh/dev/api/comm/socks_channel.md","lastUpdated":null}'),t={name:"dev/api/comm/socks_channel.md"},n=e('<h1 id="模块-liteyuki-comm-socks-channel" tabindex="-1"><strong>模块</strong> <code>liteyuki.comm.socks_channel</code> <a class="header-anchor" href="#模块-liteyuki-comm-socks-channel" aria-label="Permalink to &quot;**模块** `liteyuki.comm.socks_channel`&quot;">​</a></h1><p>基于socket的通道</p><h3 id="class-sockschannel" tabindex="-1"><em><strong>class</strong></em> <code>SocksChannel</code> <a class="header-anchor" href="#class-sockschannel" aria-label="Permalink to &quot;***class*** `SocksChannel`&quot;">​</a></h3><hr><h4 id="func-init-self-name-str" tabindex="-1"><em><strong>func</strong></em> <code>__init__(self, name: str)</code> <a class="header-anchor" href="#func-init-self-name-str" aria-label="Permalink to &quot;***func*** `__init__(self, name: str)`&quot;">​</a></h4><p><strong>说明</strong>: 初始化通道</p><p><strong>参数</strong>:</p><blockquote><ul><li>name: 通道ID</li></ul></blockquote><details><summary><b>源代码</b> 或 <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/comm/socks_channel.py#L13" target="_blank">在GitHub上查看</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">def</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;"> __init__</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(self, name: </span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">str</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">):</span></span>\n<span class="line"><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">    self</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">._name </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;"> name</span></span>\n<span class="line"><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">    self</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">._conn_send </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;"> None</span></span>\n<span class="line"><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">    self</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">._conn_recv </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;"> None</span></span>\n<span class="line"><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">    self</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">._closed </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">=</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;"> False</span></span></code></pre></div></details><hr><h4 id="func-send-self-data" tabindex="-1"><em><strong>func</strong></em> <code>send(self, data)</code> <a class="header-anchor" href="#func-send-self-data" aria-label="Permalink to &quot;***func*** `send(self, data)`&quot;">​</a></h4><p><strong>说明</strong>: 发送数据</p><p><strong>参数</strong>:</p><blockquote><ul><li>data: 数据</li></ul></blockquote><details><summary><b>源代码</b> 或 <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/comm/socks_channel.py#L25" target="_blank">在GitHub上查看</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">def</span><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;"> send</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(self, data):</span></span>\n<span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">    pass</span></span></code></pre></div></details><hr><h4 id="func-receive-self" tabindex="-1"><em><strong>func</strong></em> <code>receive(self)</code> <a class="header-anchor" href="#func-receive-self" aria-label="Permalink to &quot;***func*** `receive(self)`&quot;">​</a></h4><p><strong>说明</strong>: 接收数据</p><p><strong>返回</strong>: data: 数据</p><details><summary><b>源代码</b> 或 <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/comm/socks_channel.py#L34" target="_blank">在GitHub上查看</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">def</span><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;"> receive</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(self):</span></span>\n<span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">    pass</span></span></code></pre></div></details><hr><h4 id="func-close-self" tabindex="-1"><em><strong>func</strong></em> <code>close(self)</code> <a class="header-anchor" href="#func-close-self" aria-label="Permalink to &quot;***func*** `close(self)`&quot;">​</a></h4><p><strong>说明</strong>: 关闭通道</p><details><summary><b>源代码</b> 或 <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/comm/socks_channel.py#L43" target="_blank">在GitHub上查看</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">def</span><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;"> close</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(self):</span></span>\n<span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">    pass</span></span></code></pre></div></details>',24),l=[n];function h(o,c,p,k,r,d){return i(),a("div",null,l)}const m=s(t,[["render",h]]);export{g as __pageData,m as default};