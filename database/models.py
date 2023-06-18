from typing import Optional
from sqlmodel import Field, SQLModel

class PCRBind(SQLModel, table=True):
    __table_args__ = {'keep_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True, title='序号')
    user_id: Optional[int] = Field(default=114514, title='用户QQ')
    pcrid: int = Field(title='游戏ID')
    platform: int = Field(title='服务器编号')
    group: Optional[int] = Field(default=None, title="推送群")
    name: Optional[str] = Field(default=None, title="游戏昵称")
    jjc_notice: Optional[bool] = Field(default=True, title='竞技场提醒')
    pjjc_notice: Optional[bool] = Field(default=True, title='公主竞技场提醒')
    up_notice: Optional[int] = Field(default=False, title='上升提醒')
    online_notice: Optional[int] = Field(default=0, title='上线提醒')
    private: Optional[bool] = Field(default=False, title='私聊')
    

class Account(SQLModel, table=True):
    __table_args__ = {'keep_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True, title='序号')
    viewer_id: str = Field(title='游戏ID')
    account: str = Field(title='账号')
    password: str = Field(title='密码')
    platform: int = Field(title='服务器编号')

class JJCHistory(SQLModel, table=True):
    __table_args__ = {'keep_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True, title='序号')
    user_id : int = Field(default=114514, title='用户QQ')
    pcrid: int = Field(title='游戏ID')
    name: str = Field(title="游戏昵称")
    platform: int = Field(title='服务器编号')
    date: int = Field(title='时间戳'),
    item: int = Field(title='类型')
    before: int = Field(title='之前')
    after: int = Field(title='之后')
    is_send: bool = Field(title='发送')

