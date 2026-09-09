import { Route, Routes as RouterRoutes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { FiltersProvider } from "./hooks/useFilters";
import { DataSourceProvider } from "./hooks/useDataSource";
import Overview from "./pages/Overview";
import AirfareIndex from "./pages/AirfareIndex";
import Routes from "./pages/Routes";
import Airlines from "./pages/Airlines";
import LeadTime from "./pages/LeadTime";
import CollectionMonitor from "./pages/CollectionMonitor";
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
            <Route path="/collection" element={<CollectionMonitor />} />
            <Route path="/import" element={<ImportData />} />
            <Route path="/api" element={<APIPage />} />
          </Route>
        </RouterRoutes>
      </FiltersProvider>
    </DataSourceProvider>
  );
}
