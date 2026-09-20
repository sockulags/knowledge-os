import { BrowserRouter, Routes, Route } from "react-router";
import { Shell } from "./components/Shell";
import { Home } from "./pages/Home";
import { Project } from "./pages/Project";
import { Document } from "./pages/Document";
import { Compare } from "./pages/Compare";
import { Search } from "./pages/Search";
import { Everything } from "./pages/Everything";
import { Skill } from "./pages/Skill";
import { RepoDoc } from "./pages/RepoDoc";
import { NotFound } from "./pages/NotFound";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="p/:projectId" element={<Project />} />
          <Route path="r/:recordId" element={<Document />} />
          <Route path="r/:recordId/compare" element={<Compare />} />
          <Route path="s/:skillName" element={<Skill />} />
          <Route path="f/*" element={<RepoDoc />} />
          <Route path="search" element={<Search />} />
          <Route path="everything" element={<Everything />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
