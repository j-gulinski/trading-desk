## Quick Start & Run Instructions

The entire system, including the frontend and backend microservices, is containerized.

1. Make sure Docker is running on your machine.
2. In the root directory, build and start the cluster:
   ```bash
   docker compose up --build -d
Access the Frontend: Open your browser and navigate to http://localhost:3000

## Designs 
Figma: https://www.figma.com/design/p9oBtqRntBzxCWwECvGGkw/Untitled?node-id=0-1&p=f&t=zh97RU6kN0MLmVDC-0

## Docker Setup
Live Reloading - (./frontend:/app): This bind mount syncs the local frontend folder directly into the isolated Linux container. When a React file is saved locally, Vite's Hot Module Replacement (HMR) instantly updates the browser. Node modules is excluded to allow container to have its own.