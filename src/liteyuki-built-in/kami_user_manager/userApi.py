import smtplib
import traceback
from email.mime.text import MIMEText

from ...extraApi.base import ExtraData


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

    content = """
    <p><center><font color="84e4ff" size=6>轻</font><font color="51abff" size=6>雪</font><font color="84e4ff" size=6>科</font><font color="51abff" size=6>技</font></center>
<center><font color="84e4ff" size=2>SnowyFirefly Studio</font></center></p>

<h4>亲爱的%s:</h4>

<h4>感谢你支持轻雪机器人</h4>

<h4>以下是你的验证码</h4>

<p><font color="84e4ff" size=6>%s</font>
</br></br>
此验证码五分钟内有效，请不要告诉他人
</br></br>
<font size=3><p align="right">此致</br>轻雪科技</p></font></p>
    """ % (email, auth_code)

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
