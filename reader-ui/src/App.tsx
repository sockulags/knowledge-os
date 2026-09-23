import { createBrowserRouter, RouterProvider } from "react-router";
import { Shell } from "./components/Shell";
import { Home } from "./pages/Home";
import { Project } from "./pages/Project";
import { Document } from "./pages/Document";
import { EditRecord } from "./pages/EditRecord";
import { NewRecord } from "./pages/NewRecord";
import { Compare } from "./pages/Compare";
import { Search } from "./pages/Search";
import { Everything } from "./pages/Everything";
import { Skill } from "./pages/Skill";
import { RepoDoc } from "./pages/RepoDoc";
import { NotFound } from "./pages/NotFound";
import { Sync } from "./pages/Sync";
import { Decide } from "./pages/Decide";

// A data router (rather than <BrowserRouter>) because the editor's
// unsaved-changes guard needs useBlocker, which only data routers support.
const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { index: true, element: <Home /> },
      { path: "decide", element: <Decide /> },
      { path: "p/:projectId", element: <Project /> },
      { path: "p/:projectId/new", element: <NewRecord /> },
      { path: "r/:recordId", element: <Document /> },
      { path: "r/:recordId/edit", element: <EditRecord /> },
      { path: "r/:recordId/compare", element: <Compare /> },
      { path: "s/:skillName", element: <Skill /> },
      { path: "f/*", element: <RepoDoc /> },
      { path: "search", element: <Search /> },
      { path: "everything", element: <Everything /> },
      { path: "sync", element: <Sync /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
