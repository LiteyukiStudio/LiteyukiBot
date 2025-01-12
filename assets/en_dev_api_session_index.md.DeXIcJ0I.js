import{_ as i,c as a,a7 as e,o as n}from"./chunks/framework.v7PlT0Wt.js";const c=JSON.parse('{"title":"liteyuki.session","description":"","frontmatter":{"title":"liteyuki.session","collapsed":true},"headers":[],"relativePath":"en/dev/api/session/index.md","filePath":"en/dev/api/session/index.md","lastUpdated":null}'),t={name:"en/dev/api/session/index.md"};function l(h,s,k,p,r,d){return n(),a("div",null,s[0]||(s[0]=[e('<h1 id="module-liteyuki-session" tabindex="-1"><strong>Module</strong> <code>liteyuki.session</code> <a class="header-anchor" href="#module-liteyuki-session" aria-label="Permalink to &quot;**Module** `liteyuki.session`&quot;">​</a></h1><p>该模块参考并引用了nonebot-plugin-alconna的消息段定义</p><hr><h3 id="func-message-handler-thread-i-chans-iterable-chan-any" tabindex="-1"><em><strong>func</strong></em> <code>message_handler_thread(i_chans: Iterable[Chan[Any]])</code> <a class="header-anchor" href="#func-message-handler-thread-i-chans-iterable-chan-any" aria-label="Permalink to &quot;***func*** `message_handler_thread(i_chans: Iterable[Chan[Any]])`&quot;">​</a></h3><p><strong>Arguments</strong>:</p><blockquote><ul><li>i_chans: 多路输入管道组</li></ul></blockquote><details><summary><b>Source code</b> or <a href="https://github.com/LiteyukiStudio/LiteyukiBot/tree/main/liteyuki/session/__init__.py#L15" target="_blank">View on GitHub</a></summary><div class="language-python vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang">python</span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">def</span><span style="--shiki-light:#6F42C1;--shiki-dark:#B392F0;"> message_handler_thread</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">(i_chans: Iterable[Chan[Any]]):</span></span>\n<span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">    for</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;"> msg </span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">in</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;"> select(</span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">*</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">i_chans):</span></span>\n<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">        logger.debug(</span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">f</span><span style="--shiki-light:#032F62;--shiki-dark:#9ECBFF;">&#39;Recv from anybot </span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">{</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">msg</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">}</span><span style="--shiki-light:#032F62;--shiki-dark:#9ECBFF;">&#39;</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">)</span></span>\n<span class="line"><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">        logger.info(</span><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">f</span><span style="--shiki-light:#032F62;--shiki-dark:#9ECBFF;">&#39;Recv from anybot </span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">{</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">msg</span><span style="--shiki-light:#005CC5;--shiki-dark:#79B8FF;">}</span><span style="--shiki-light:#032F62;--shiki-dark:#9ECBFF;">&#39;</span><span style="--shiki-light:#24292E;--shiki-dark:#E1E4E8;">)</span></span>\n<span class="line"><span style="--shiki-light:#D73A49;--shiki-dark:#F97583;">    pass</span></span></code></pre></div></details>',7)]))}const g=i(t,[["render",l]]);export{c as __pageData,g as default};