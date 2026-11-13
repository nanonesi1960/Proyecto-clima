import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# 1. DEFINIR LA VARIABLE DATABASE_URL Y ADAPTARLA PARA PSYCOPG
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

# 2. TABLA EN BASE DE DATOS
class RegistroDB(Base):
    __tablename__ = "lecturas"
    id = Column(Integer, primary_key=True, index=True)
    estacion_id = Column(String, index=True, nullable=False)
    temperatura = Column(Float, nullable=False)
    presion = Column(Float, nullable=False)
    fecha_hora = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# 3. ESQUEMAS DE DATOS JSON
class LecturaEntrada(BaseModel):
    estacion_id: str = Field(..., min_length=2, max_length=50)
    temperatura: float = Field(..., ge=-50.0, le=100.0)
    presion: float = Field(..., ge=300.0, le=1200.0)

class LecturaSalida(BaseModel):
    id: int
    estacion_id: str
    temperatura: float
    presion: float
    fecha_hora: datetime

    class Config:
        from_attributes = True

# 4. APLICACIÓN FASTAPI
app = FastAPI(title="API Estaciones Clima")

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

# 5. RUTAS DE LA API
@app.get("/")
def inicio():
    return {"mensaje": "Servidor activo y conectado a la base de datos"}

@app.post("/api/lecturas", response_model=LecturaSalida, status_code=201)
def guardar_dato(datos: LecturaEntrada, x_api_key: str = Header(None), db: Session = Depends(get_db)):
    if x_api_key != API_KEY_VALIDA:
        raise HTTPException(status_code=401, detail="Contraseña API Key incorrecta")

    nueva_fila = RegistroDB(
        estacion_id=datos.estacion_id,
        temperatura=datos.temperatura,
        presion=datos.presion
    )
    db.add(nueva_fila)
    db.commit()
    db.refresh(nueva_fila)
    return nueva_fila

@app.get("/api/lecturas", response_model=List[LecturaSalida])
def leer_datos(estacion: Optional[str] = None, limite: int = 50, db: Session = Depends(get_db)):
    consulta = db.query(RegistroDB)
    if estacion:
        consulta = consulta.filter(RegistroDB.estacion_id == estacion)
    registros = consulta.order_by(RegistroDB.fecha_hora.desc()).limit(limite).all()
    return list(reversed(registros))
