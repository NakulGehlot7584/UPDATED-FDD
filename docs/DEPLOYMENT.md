# Open-FDD Production Deployment Guide

This guide covers running the application locally and deploying the system to production with:
- **Backend**: Hosted on [Render](https://render.com) (Python / FastAPI)
- **Frontend**: Hosted on [Vercel](https://vercel.com) (Vite / React / TypeScript)

---

## 1. Local Development

### Backend
1. Create and activate a Python virtual environment (Python 3.10+):
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
   ```
4. Local API Health Check:
   ```text
   http://127.0.0.1:8000/api/health
   ```

### Frontend
1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The frontend runs on `http://localhost:3000` and automatically proxies `/api` requests to `http://127.0.0.1:8000` via [vite.config.ts](file:///D:/UPDATED-FDD/frontend/vite.config.ts).

---

## 2. Render Deployment (Backend)

The backend is configured as a Python Web Service on Render using the included [render.yaml](file:///D:/UPDATED-FDD/render.yaml) blueprint or manual creation.

### Service Specifications
- **Service Type**: Web Service
- **Environment**: Python 3
- **Root Directory**: Repository root (`.`) or specify app dir
- **Build Command**:
  ```bash
  pip install -r backend/requirements.txt
  ```
- **Start Command**:
  ```bash
  uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
  ```
- **Health Check Path**: `/api/health`

### Persistent Disk Requirement
The application stores uploaded raw CSV files and generated Hive-partitioned Parquet historian data. To persist data across server restarts and deploys, attach a **Persistent Disk**:
- **Mount Path**: `/var/data`
- **Recommended Size**: 10 GB+

### Required Environment Variables
Configure these in the Render Dashboard under **Environment**:
| Variable Name | Value | Description |
|---|---|---|
| `PYTHON_VERSION` | `3.11.9` | Recommended Python runtime |
| `CORS_ORIGINS` | `https://YOUR-VERCEL-DOMAIN.vercel.app` | Comma-separated list of allowed frontend origins (e.g. your Vercel URL) |
| `OPENFDD_UPLOAD_DIR` | `/var/data/uploads` | Path to upload directory on the persistent disk |
| `OPENFDD_STORAGE_DIR` | `/var/data/historian` | Path to historian directory on the persistent disk |
| `OPENFDD_PARQUET_ROOT` | `/var/data/historian` | Parquet root path matching historian directory |

---

## 3. Vercel Deployment (Frontend)

Deploy the frontend directory to Vercel as a single-page application.

### Project Settings
- **Framework Preset**: Vite
- **Root Directory**: `frontend`
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Install Command**: `npm install`

### Required Environment Variables
Configure in the Vercel Project Settings under **Environment Variables**:
| Variable Name | Example Value | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `https://YOUR-RENDER-SERVICE.onrender.com` | Base URL of the deployed Render backend |

> **Note**: When `VITE_API_BASE_URL` is set, the frontend automatically routes all `/api` calls (e.g. `/api/health`, `/api/datasets`, `/api/fdd/execute`) to the Render backend.

---

## 4. CORS Configuration

To allow secure communication between the Vercel frontend and the Render backend:
1. Copy your Vercel deployment URL (e.g., `https://open-fdd.vercel.app`).
2. Add this URL to the `CORS_ORIGINS` environment variable in your Render service settings:
   ```text
   CORS_ORIGINS=https://open-fdd.vercel.app
   ```
3. Multiple origins can be specified by separating them with commas:
   ```text
   CORS_ORIGINS=https://open-fdd.vercel.app,http://localhost:3000
   ```
