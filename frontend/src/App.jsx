import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import NewResearch from './pages/NewResearch'
import ResearchLive from './pages/ResearchLive'
import History from './pages/History'
import Settings from './pages/Settings'

export default function App(){
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<NewResearch/>}/>
          <Route path="/research/:id" element={<ResearchLive/>}/>
          <Route path="/history" element={<History/>}/>
          <Route path="/settings" element={<Settings/>}/>
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
