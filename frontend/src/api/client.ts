import axios from "axios";

export const api = axios.create({
  baseURL: "/api", // <-- Было localhost:8000/api
  headers: {
    "Content-Type": "application/json"
  }
});
