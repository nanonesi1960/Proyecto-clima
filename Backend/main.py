import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./estaciones.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

API_KEY_VALIDA = os.getenv("API_KEY", "mi_clave_secreta_1234")

class RegistroDB(Base):
    __tablename__ = "lecturas"
    id = Column(Integer, primary_key=True, index=True)
    estacion_id = Column(String, index=True, nullable=False)
    temperatura = Column(Float, nullable=False)
    presion = Column(Float, nullable=False)
    humedad = Column(Float, nullable=True) # Nueva columna para el GY-21
    fecha_hora = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# Agregar automáticamente la columna 'humedad' si la tabla ya existía de antes
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE lecturas ADD COLUMN humedad FLOAT;"))
    except Exception:
        pass # Si la columna ya existe, ignora el aviso y sigue

class LecturaEntrada(BaseModel):
    estacion_id: str = Field(..., min_length=2, max_length=50)
    temperatura: float = Field(..., ge=-50.0, le=100.0)
    presion: float = Field(..., ge=0.0, le=1200.0)
    humedad: Optional[float] = Field(None, ge=0.0, le=100.0)

class LecturaSalida(BaseModel):
    id: int
    estacion_id: str
    temperatura: float
    presion: float
    humedad: Optional[float] = None
    fecha_hora: datetime

    class Config:
        from_attributes = True

app = FastAPI(title="API Estaciones Clima + Humedad")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def inicio():
    return {"mensaje": "Servidor activo con soporte de Temperatura, Presion y Humedad"}

@app.post("/api/lecturas", response_model=LecturaSalida, status_code=201)
def guardar_dato(datos: LecturaEntrada, x_api_key: str = Header(None), db: Session = Depends(get_db)):
    if x_api_key != API_KEY_VALIDA:
        raise HTTPException(status_code=401, detail="Contraseña API Key incorrecta")

    nueva_fila = RegistroDB(
        estacion_id=datos.estacion_id,
        temperatura=datos.temperatura,
        presion=datos.presion,
        humedad=datos.humedad
    )
    db.add(nueva_fila)
    db.commit()
    db.refresh(nueva_fila)
    return nueva_fila

@app.get("/api/lecturas", response_model=List[LecturaSalida])
def leer_datos(estacion: Optional[str] = None, limite: int = 100, db: Session = Depends(get_db)):
    consulta = db.query(RegistroDB)
    if estacion:
        consulta = consulta.filter(RegistroDB.estacion_id == estacion)
    registros = consulta.order_by(RegistroDB.fecha_hora.desc()).limit(limite).all()
    return list(reversed(registros))
