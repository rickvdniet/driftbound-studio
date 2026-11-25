import { Badge, Card, Loading, stateTone } from "../components/ui";
import { useData } from "../hooks/useData";

export function Projects() {
  const { data, error } = useData<any[]>("/projects", 5000);
  if (!data) return <Loading error={error} />;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Production</h1>
      <Card>
        {!data.length ? <p className="text-sm text-white/50">No projects yet. Approve a concept and choose "Start production".</p> : (
          <table><thead><tr><th>Project</th><th>Stage</th><th>Category</th><th>Duration</th><th>Updated</th></tr></thead><tbody>
            {data.map((p) => (
              <tr key={p.id} className="hover:bg-white/5">
                <td><a className="text-gold hover:underline" href={`#projects/${p.id}`}>{p.name}</a></td>
                <td><Badge tone={stateTone(p.state)}>{p.state}</Badge></td><td>{p.category}</td><td>{p.duration_hours} h</td>
                <td className="text-white/50">{new Date(p.updated_at).toLocaleString()}</td>
              </tr>))}
          </tbody></table>)}
      </Card>
    </div>
  );
}
