# Despliegue en AWS Academy (EC2) — ZonaVip Entrega 2

Guía paso a paso para levantar todo el ecosistema (Nginx + Django + 2
microservicios Flask + PostgreSQL + Redis + Celery) en una instancia **EC2 de
AWS Academy** con un solo `docker compose up`.

---

## 1. Crear la instancia EC2

1. Entra a **AWS Academy → Learner Lab → Start Lab** y abre la consola de AWS.
2. **EC2 → Launch Instance**:
   - **Name:** `zonavip-entrega2`
   - **AMI:** Amazon Linux 2023 (o Ubuntu 22.04).
   - **Tipo:** `t2.medium` o superior (recomendado: 2 vCPU / 4 GB; son 7
     contenedores).
   - **Key pair:** crea/usa uno para conectarte por SSH.
   - **Security Group** — abre estos puertos (Inbound rules):
     | Tipo | Puerto | Origen |
     |---|---|---|
     | SSH | 22 | Tu IP |
     | HTTP | 80 | 0.0.0.0/0 |
3. **Launch**. Luego asigna una **IP elástica** (EC2 → Elastic IPs → Allocate →
   Associate a la instancia) para que la IP no cambie — esa es la IP que
   entregas en la plataforma.

---

## 2. Conectarse e instalar Docker

```bash
ssh -i tu-llave.pem ec2-user@<IP-ELASTICA>

# --- Amazon Linux 2023 ---
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Instalar el plugin de Docker Compose v2
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
     -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Reconecta la sesión SSH para aplicar el grupo docker
exit
```

> En **Ubuntu**: `sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin git` y luego `sudo systemctl enable --now docker`.

---

## 3. Clonar y levantar el proyecto

```bash
ssh -i tu-llave.pem ec2-user@<IP-ELASTICA>

git clone https://github.com/jcgomezj/ZonaVip---T-picos-ing.-de-software.git
cd ZonaVip---T-picos-ing.-de-software

# (Opcional) configurar la URL del servicio del equipo aliado
export ALIADO_API_URL="http://<ip-del-aliado>/api/v2/integracion/info"

# Construir y levantar todo el ecosistema en segundo plano
docker compose up --build -d

# Ver el estado de los 7 servicios
docker compose ps
```

La aplicación queda disponible en:

```
http://<IP-ELASTICA>/
```

---

## 4. Verificar el despliegue

```bash
# Frontend (monolito Django)
curl -I http://<IP-ELASTICA>/

# API versionada legacy -> Django
curl http://<IP-ELASTICA>/api/v1/eventos/

# Microservicio QR (estrangulado, Entrega 1)
curl http://<IP-ELASTICA>/api/v2/qr/health

# Microservicio de Integración (estrangulado, Entrega 2)
curl http://<IP-ELASTICA>/api/v2/integracion/health
curl http://<IP-ELASTICA>/api/v2/integracion/info
curl "http://<IP-ELASTICA>/api/v2/integracion/clima?ciudad=Medellin"

# Tarea asíncrona (Celery + Redis): encolar y consultar
TASK=$(curl -s -X POST http://<IP-ELASTICA>/api/v1/reportes/ventas/ -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json;print(json.load(sys.stdin)['task_id'])")
curl http://<IP-ELASTICA>/api/v1/tareas/$TASK/
```

### Crear datos de ejemplo (opcional, para ver eventos en el frontend)

```bash
docker compose exec django_web python manage.py createsuperuser
# Luego entra a http://<IP-ELASTICA>/admin/ y crea una Categoría, un
# Organizador, un Evento (estado PUBLICADO) y una Localidad.
```

---

## 5. Operación

```bash
docker compose logs -f django_web      # logs del monolito
docker compose logs -f celery_worker   # logs del worker asíncrono
docker compose logs -f nginx           # logs del gateway

docker compose restart                 # reiniciar todo
docker compose down                    # detener (conserva el volumen de la BD)
docker compose down -v                 # detener y borrar también la BD
```

> **Importante para la sustentación:** mantén la instancia EC2 **encendida** y
> la IP elástica asociada. Entrega en la plataforma el enlace del repo
> (rama `main`) y la **IP elástica**.

---

## 6. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `docker: permission denied` | El usuario no está en el grupo `docker` | Reconecta el SSH tras `usermod -aG docker` |
| `502 Bad Gateway` en `/` | Django aún migrando/arrancando | Espera ~30s; mira `docker compose logs django_web` |
| El reporte async no termina | Worker o Redis caídos | `docker compose ps`; revisa `celery_worker` y `redis` |
| `/api/v2/integracion/aliado` dice "no disponible" | `ALIADO_API_URL` no configurada o aliado caído | Define la env var y `docker compose up -d` de nuevo (es resiliente a propósito) |
| Memoria insuficiente / contenedores reiniciando | Instancia pequeña | Usa `t2.medium` o mayor |
