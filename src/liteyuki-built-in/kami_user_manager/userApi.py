import smtplib
import traceback
import os
from email.mime.text import MIMEText

from ...extraApi.base import ExConfig, ExtraData


async def sendAuthCode(email: str, auth_code: str):
    """
    :param auth_code:
    :param email:
    :return:

    发送邮箱验证码,请在此前校验邮箱格式
    """
    mail_host = await ExtraData.get_global_data(key="kami.base.email_host", default="")
    mail_user = await ExtraData.get_global_data(key="kami.base.email_user", default="")
    mail_auth = await ExtraData.get_global_data(key="kami.base.email_auth", default="")

    sender = await ExtraData.get_global_data(key="kami.base.email", default="")

    receivers = [email]

    with open(os.path.join(ExConfig.root_path, "resource", "customize", "email_text.html"), encoding="utf-8") as f:
        content = f.read()
        try:
            content = content.replace("#auth_code#", auth_code)
            content = content.replace("#email#", email)
        except:
            pass
        f.close()
    message = MIMEText(content, "html", "utf-8")
    message["Subject"] = "LiteYuki-轻雪验证码"
    message["From"] = sender
    message["To"] = receivers[0]
    try:
        smtpObj = smtplib.SMTP()
        smtpObj.connect(mail_host, 25)
        smtpObj.login(mail_user, mail_auth)
        print(message)
        smtpObj.sendmail(sender, receivers, msg=message.as_string())
        return True
    except smtplib.SMTPException as e:
        traceback.print_exc()
        return False
