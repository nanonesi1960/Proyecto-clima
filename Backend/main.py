# 1. IMPORTAR HERRAMIENTAS
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# 2. CONECTAR A LA BASE DE DATOS
# Busca la dirección de la base de datos en Render. Si no la encuentra, crea un archivo local.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./estaciones.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Contraseña secreta para que solo tus ESP32 puedan enviar datos
API_KEY_VALIDA = os.getenv("API_KEY", "mi_clave_secreta_1234")

# 3. DISEÑAR LA TABLA DE LA BASE DE DATOS (Como una hoja de Excel)
class RegistroDB(Base):
    __tablename__ = "lecturas" # Nombre de la tabla
    id = Column(Integer, primary_key=True, index=True)       # Número de fila (1, 2, 3...)
    estacion_id = Column(String, index=True, nullable=False) # Ej: "EST-01"
    temperatura = Column(Float, nullable=False)              # Ej: 24.5
    presion = Column(Float, nullable=False)                  # Ej: 1013.2
    fecha_hora = Column(DateTime, default=lambda: datetime.now(timezone.utc)) # Hora exacta

# Crea la tabla si todavía no existe
Base.metadata.create_all(bind=engine)

# 4. REGLAS DE VALIDACIÓN (Qué datos aceptamos del ESP32)
class LecturaEntrada(BaseModel):
    estacion_id: str = Field(..., min_length=2, max_length=50)
    temperatura: float = Field(..., ge=-50.0, le=100.0) # Solo acepta entre -50°C y 100°C
    presion: float = Field(..., ge=300.0, le=1200.0)    # Solo acepta entre 300 y 1200 hPa

# Formato en el que devolveremos los datos a la página web
class LecturaSalida(BaseModel):
    id: int
    estacion_id: str
    temperatura: float
    presion: float
    fecha_hora: datetime

    class Config:
        from_attributes = True

# 5. CREAR LA APLICACIÓN SERVIDOR
app = FastAPI(title="API Estaciones Clima")

# Permitir que cualquier página web pueda leer los datos sin bloqueos de seguridad
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Función auxiliar para abrir y cerrar la base de datos en cada consulta
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 6. LAS PUERTAS DE ENTRADA (RUTAS / ENDPOINTS)

# Puerta A: Para probar desde el navegador si el servidor está vivo
@app.get("/")
def inicio():
    return {"mensaje": "¡El servidor está funcionando perfectamente!"}

# Puerta B: Por aquí entra el ESP32 a dejar datos (Método POST)
@app.post("/api/lecturas", response_model=LecturaSalida, status_code=201)
def guardar_dato(datos: LecturaEntrada, x_api_key: str = Header(None), db: Session = Depends(get_db)):
    # Verificar si el ESP32 trajo la contraseña correcta
    if x_api_key != API_KEY_VALIDA:
        raise HTTPException(status_code=401, detail="Contraseña API Key incorrecta")

    # Crear una fila nueva con los datos recibidos
    nueva_fila = RegistroDB(
        estacion_id=datos.estacion_id,
        temperatura=datos.temperatura,
        presion=datos.presion
    )
    db.add(nueva_fila)      # Agregar a la tabla
    db.commit()             # Guardar cambios permanentemente
    db.refresh(nueva_fila)  # Obtener el ID y la fecha generados
    return nueva_fila       # Responderle al ESP32 que todo salió bien

# Puerta C: Por aquí entra la Página Web a pedir datos (Método GET)
@app.get("/api/lecturas", response_model=List[LecturaSalida])
def leer_datos(estacion: Optional[str] = None, limite: int = 50, db: Session = Depends(get_db)):
    consulta = db.query(RegistroDB)
    # Si la web pidió una estación en particular, filtramos
    if estacion:
        consulta = consulta.filter(RegistroDB.estacion_id == estacion)
    
    # Traer los últimos 50 registros y ordenarlos del más viejo al más nuevo para el gráfico
    registros = consulta.order_by(RegistroDB.fecha_hora.desc()).limit(limite).all()
    return list(reversed(registros))
