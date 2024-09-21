"""
Module docs
"""
import requests  # type: ignore
import zipfile

from github import Github, InputGitTreeElement, GitTree
from github.Issue import Issue
from github.Repository import Repository
import json
import yaml

from liteyuki_flow.const import OPENED, EDITED, CLOSED, REOPENED, RESOURCE_JSON, bot_id, edit_tip
from liteyuki_flow.markdown_parser import MarkdownParser
from liteyuki_flow.typ import err, nil

user_agent = "liteyuki-flow"

headers = {
    "User-Agent": user_agent
}


def push_check_result(issue: Issue, result: str):
    cid = None
    for cm in issue.get_comments():
        if cm.body.startswith("检查结果") and cm.user.login == bot_id:
            cid = cm.id
            break
    if cid is not None:
        issue.get_comment(cid).edit("检查结果: " + result)
    else:
        issue.create_comment("检查结果: " + result)


def push_publish_result(issue: Issue, result: str):
    cid = None
    for cm in issue.get_comments():
        if cm.body.startswith("发布结果") and cm.user.login == bot_id:
            cid = cm.id
            break
    if cid is not None:
        issue.get_comment(cid).edit("发布结果: " + result)
    else:
        issue.create_comment("发布结果: " + result)


# opened: 创建新的资源包，预审核
# edited: 编辑资源包信息，需重新审核
# closed: 审核通过，修改json并提交
# reopened: 重新打开，无操作
def on_first_open(github: Github, issue: Issue, repo: Repository):
    issue.create_comment("已收到资源包发布请求，我会马上开始预检. " + edit_tip)
    push_check_result(issue, "请等待")
    issue.add_to_labels("Resource")


# opened | edited
def pre_check(github: Github, issue: Issue, repo: Repository) -> err:
    parser = MarkdownParser(issue.body)
    parser.parse_front_matters()
    name = parser.front_matters.get("name")
    desc = parser.front_matters.get("desc")
    link = parser.front_matters.get("link")
    homepage = parser.front_matters.get("homepage")  # optional
    author = parser.front_matters.get("author")

    if not all((name, desc, link, author)):
        push_check_result(issue, "❌ name, desc, link, homepage 及 author 为必填字段.")
        return ValueError("name, desc, link, homepage 及 author 为必填字段.")

    # 下载并解析资源包
    r = requests.get(link, headers=headers)
    if r.status_code != 200:
        push_check_result(issue, "❌ 下载失败.")
        return ValueError("下载失败.")
    try:
        with open(f"{name}.zip", "wb") as f:
            f.write(r.content)
        # 解压
        with zipfile.ZipFile(f"{name}.zip", "r") as z:
            z.extractall(f"{name}")
        # 检测包内metadata.yml文件
        data = yaml.load(open(f"{name}/metadata.yml"), Loader=yaml.SafeLoader)
    except Exception as e:
        push_check_result(issue, "❌ 解析资源包失败，可能是格式问题或metadata.yml不存在: " + str(e))
        return e

    # 检测必要字段 name，description，version
    if not all((data.get("name"), data.get("description"), data.get("version"))):
        push_check_result(issue, "❌ 元数据中缺少必要字段 name, description 或 version.")
        return ValueError("元数据中缺少必要字段 name, description 或 version.")

    # 不检测重复资源包，因为资源包可能有多个版本
    # 检测通过，编辑原issue
    metadata_markdown = f"**名称**: {data.get('name')}\n**描述**: {data.get('description')}\n**版本**: {data.get('version')}\n"
    for k, v in data.items():
        if k not in ("name", "description", "version"):
            metadata_markdown += f"**{k}**: {v}\n"

    new_issue_body = f"---\nname: {name}\ndesc: {desc}\nlink: {link}\nhomepage: {homepage}\nauthor: {author}\n---\n"

    publish_info = f"## 发布信息\n"
    publish_info += f"**名称**: {name}\n"
    publish_info += f"**描述**: {desc}\n"
    publish_info += f"**作者**: {author}\n"
    publish_info += f"**主页**: {homepage}\n"
    publish_info += f"**下载**: {link}\n"
    # 遍历其他字段
    for k, v in data.items():
        if k not in ("name", "description", "version"):
            new_issue_body += f"**{k}**: {v}\n"

    issue.edit(title=f"Resource: {name}")
    issue.add_to_labels("pre-checked")
    push_check_result(issue, f"✅ 预检查通过，等待管理员人工审核\n{publish_info}\n## 元数据\n{metadata_markdown}")
    return nil


# closed
def add_resource(github: Github, issue: Issue, repo: Repository) -> err:
    # 检测关闭时是否有管理员发布的通过评论
    try:
        if "pre-checked" not in [l.name for l in issue.labels]:
            issue.edit(state="open")
            push_publish_result(issue, "❌ 请先通过预检查。")
            return ValueError("请先进行预检查。")

        # 检测评论
        for cm in issue.get_comments():
            if cm.body.startswith(("通过", "pass",)):
                # 检测用户是否是管理员
                if cm.user.login not in [u.login for u in repo.get_collaborators()]:
                    issue.edit(state="open")
                    push_publish_result(issue, "❌ 你不是仓库管理员，无法发布资源包。")
                    return ValueError("你不是仓库管理员，无法发布资源包。")
                break
        else:
            issue.edit(state="open")
            push_publish_result(issue, "❌ 管理员未审核。")
            return ValueError("管理员未审核。")

        parser = MarkdownParser(issue.body)
        parser.parse_front_matters()
        name = parser.front_matters.get("name")
        desc = parser.front_matters.get("desc")
        link = parser.front_matters.get("link")
        homepage = parser.front_matters.get("homepage")  # optional
        author = parser.front_matters.get("author")

        # 编辑仓库内的json文件
        resources = json.load(open(RESOURCE_JSON))
        resources.append({
            "name": name,
            "description": desc,
            "link": link,
            "homepage": homepage,
            "author": author
        })
        ref = repo.get_git_ref("heads/main")
        tree = repo.create_git_tree(
            base_tree=repo.get_git_commit(ref.object.sha).tree,
            tree=[
                InputGitTreeElement(
                    path=RESOURCE_JSON,
                    mode="100644",
                    type="blob",
                    content=json.dumps(resources, indent=4, ensure_ascii=False)
                )
            ]
        )
        commit = repo.create_git_commit(
            message=f":package: 发布资源: {name}",
            tree=tree,
            parents=[repo.get_git_commit(ref.object.sha)]
        )
        ref.edit(commit.sha)
        if "pre-checked" in [l.name for l in issue.labels]:
            issue.remove_from_labels("pre-checked")
        issue.add_to_labels("published")
        push_publish_result(issue, f"✅ 资源包 {name} 已发布！商店页面稍后就会更新。")
        return nil
    except Exception as e:
        issue.edit(state="open")
        push_publish_result(issue, f"❌ 发布失败: {str(e)}")
        return e


def handle_resource(github: Github, issue: Issue, repo: Repository, act_type: str):
    if act_type in (OPENED, EDITED):
        if act_type == OPENED:
            on_first_open(github, issue, repo)
        pre_check(github, issue, repo)
    elif act_type == CLOSED:
        e = add_resource(github, issue, repo)
        if e != nil:
            print(f"Error: {e}")
    else:
        print("No operation found for the issue: ", act_type)
