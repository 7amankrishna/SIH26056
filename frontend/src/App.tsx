import { Navigate, Route, Routes as RouterRoutes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { FiltersProvider } from "./hooks/useFilters";
import { DataSourceProvider } from "./hooks/useDataSource";
import Overview from "./pages/Overview";
import AirfareIndex from "./pages/AirfareIndex";
import Routes from "./pages/Routes";
import Airlines from "./pages/Airlines";
import LeadTime from "./pages/LeadTime";
import MethodologyPage from "./pages/MethodologyPage";
import APIPage from "./pages/APIPage";
import ImportData from "./pages/ImportData";

export default function App() {
  return (
    <DataSourceProvider>
      <FiltersProvider>
        <RouterRoutes>
          <Route element={<Layout />}>
            <Route path="/" element={<Overview />} />
            <Route path="/index" element={<AirfareIndex />} />
            <Route path="/routes" element={<Routes />} />
            <Route path="/airlines" element={<Airlines />} />
            <Route path="/lead-time" element={<LeadTime />} />
            <Route path="/import" element={<ImportData />} />
            <Route path="/methodology" element={<MethodologyPage />} />
            <Route path="/api" element={<APIPage />} />
            {/* Legacy links should recover instead of rendering a blank route.
                The Data Quality and Collection Monitor dashboard pages were
                intentionally removed from the product navigation. */}
            <Route path="/quality" element={<Navigate to="/" replace />} />
            <Route path="/collection" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </RouterRoutes>
      </FiltersProvider>
    </DataSourceProvider>
  );
}
