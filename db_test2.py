import json
import random

from src.api.data import LiteModel, SqliteORMAdapter


class Score(LiteModel):
    subject: str
    score: int


class Student(LiteModel):
    name: str
    age: str
    sex: str
    scores: list[Score] = []


class Teacher(LiteModel):
    name: str
    age: str


class Class(LiteModel):
    name: str
    students: list[Student]
    test_json: dict[str, Student] = {'张三': Student}


class University(LiteModel):
    name: str
    address: str
    rank: int = 0
    classes: list[Class] = []
    students: list[Student] = []


cqupt = University(name='重庆邮电大学', address='重庆', rank=100)
pku = University(name='北京大学', address='北京', rank=1)
cqu = University(name='重庆大学', address='重庆', rank=10)

student_name_list = ['张三', '李四', '王五', '赵六', '钱七', '孙八', '周九', '吴十']
student_list = [Student(name=name, age=19, sex=random.choice(['男', '女'])) for name in student_name_list]
# 构建复杂模型进行数据库测试
cqupt.students = student_list
cqupt.classes = [Class(name='软件工程', students=student_list, test_json={name: student for name, student in zip(student_name_list, student_list)})]
for student in student_list:
    student.scores = [Score(subject='语文', score=random.randint(60, 100)), Score(subject='数学', score=random.randint(60, 100)),
                      Score(subject='英语', score=random.randint(60, 100))]
    student.scores.append(Score(subject='物理', score=random.randint(60, 100)))
    student.scores.append(Score(subject='化学', score=random.randint(60, 100)))
    student.scores.append(Score(subject='生物', score=random.randint(60, 100)))
    student.scores.append(Score(subject='历史', score=random.randint(60, 100)))
    student.scores.append(Score(subject='地理', score=random.randint(60, 100)))
    student.scores.append(Score(subject='政治', score=random.randint(60, 100))
    )
print(json.dumps(cqupt.dict(), indent=4, ensure_ascii=False))
db = SqliteORMAdapter('test2.db')
db.auto_migrate(University, Class, Student, Score)
db.save(cqupt)

# 查询测试
db.first(University, 'name = ?', '重庆邮电大学')