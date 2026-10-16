from shared.database.session import make_session_factory

# JIT désactivé : sur les requêtes courtes du tableau de bord (hypertable découpée en nombreux chunks), la
# compilation JIT coûte plusieurs secondes pour un gain nul (mesuré : 4,2 s de JIT pour 0,3 s d'exécution).
engine, SessionLocal = make_session_factory(connect_args={"options": "-c jit=off"})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
