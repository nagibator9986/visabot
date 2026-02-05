import { createBrowserRouter, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout/Layout";
import { UsersPage } from "@/pages/Users/UsersPage";
import { LeadFormPage } from "@/pages/LeadForm/LeadFormPage";
import { VisasPage } from "@/pages/Visas/VisasPage";
import { VisaDetailPage } from "@/pages/Visas/VisaDetailPage";
import { SettingsPage } from "@/pages/Settings/SettingsPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <Layout>
        <UsersPage />
      </Layout>
    )
  },
  {
    path: "/users",
    element: (
      <Layout>
        <UsersPage />
      </Layout>
    )
  },
  {
    path: "/users/:id/form",
    element: (
      <Layout>
        <LeadFormPage />
      </Layout>
    )
  },
  {
    path: "/visas",
    element: (
      <Layout>
        <VisasPage />
      </Layout>
    )
  },
  {
    path: "/visas/:code",
    element: (
      <Layout>
        <VisaDetailPage />
      </Layout>
    )
  },
  {
    path: "/settings",
    element: (
      <Layout>
        <SettingsPage />
      </Layout>
    )
  },
  {
    path: "*",
    element: <Navigate to="/users" replace />
  }
]);
