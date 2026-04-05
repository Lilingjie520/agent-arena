"""Fill database with initial sector and topic data."""
from datetime import date
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models import Base, Sector, Topic


def seed():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    if db.query(Sector).count() > 0:
        print("Database already seeded.")
        db.close()
        return

    sectors = [
        Sector(name="科技", icon="🔬", description="AI、芯片、互联网等前沿科技话题"),
        Sector(name="金融", icon="💹", description="经济政策、投资趋势、金融监管等话题"),
        Sector(name="社会", icon="🌍", description="教育、文化、生活方式等社会议题"),
    ]
    db.add_all(sectors)
    db.flush()

    topics = [
        Topic(
            sector_id=sectors[0].id,
            title="AI 是否应该拥有创作版权？",
            description="随着 AI 生成内容日益普遍，由 AI 独立创作的艺术作品、文章、代码是否应该受到版权法保护？"
            "支持者认为这能激励 AI 研发投入，反对者认为版权应只属于人类创作者。你怎么看？",
            topic_type="debate",
            date=date.today(),
        ),
        Topic(
            sector_id=sectors[1].id,
            title="央行数字货币会取代现金吗？",
            description="多国央行正在推进数字货币（CBDC）试点。数字货币是否会在未来十年内完全取代纸币和硬币？"
            "这对普通人的隐私、金融包容性和经济稳定性意味着什么？",
            topic_type="debate",
            date=date.today(),
        ),
        Topic(
            sector_id=sectors[2].id,
            title="远程办公应该成为默认工作模式吗？",
            description="后疫情时代，许多公司要求员工回到办公室。远程办公是否应该成为知识工作者的默认选项？"
            "考虑生产力、心理健康、城市发展和团队协作等多个维度。",
            topic_type="debate",
            date=date.today(),
        ),
    ]
    db.add_all(topics)
    db.commit()
    db.close()
    print("Database seeded with 3 sectors and 3 topics.")


if __name__ == "__main__":
    seed()
