# Plotter for Engine!B4 (staged ready-to-paste in cell Engine!D4).
import math,numpy as np,matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc,Circle,Polygon
_LF=0.12;_SF=0.06
def _ext(d):
    xs=[v[0]for v in d["nodes"].values()];ys=[v[1]for v in d["nodes"].values()]
    return max(max(xs)-min(xs),max(ys)-min(ys),1e-9)
def _dsup(ax,x,y,s,sz):
    ux,uy,rz=s
    if not(ux or uy or rz):return
    if uy or not ux:
        ax.add_patch(Polygon([(x,y),(x-sz/2,y-sz),(x+sz/2,y-sz)],closed=True,fc="0.6",ec="black",zorder=3))
        by=y-sz
        if rz:
            hy=by-sz*.15
            ax.plot([x-sz*.7,x+sz*.7],[hy,hy],color="black",lw=1,zorder=3)
            for hx in np.linspace(x-sz*.6,x+sz*.6,5):
                ax.plot([hx,hx-sz*.15],[hy,hy-sz*.2],color="black",lw=.8,zorder=3)
        elif ux!=uy:
            for cx in np.linspace(x-sz*.3,x+sz*.3,2):
                ax.add_patch(Circle((cx,by-sz*.12),sz*.12,fc="0.6",ec="black",zorder=3))
    else:
        ax.add_patch(Polygon([(x,y),(x-sz,y-sz/2),(x-sz,y+sz/2)],closed=True,fc="0.6",ec="black",zorder=3))
def _farrow(ax,x,y,gx,gy,L,lbl):
    mg=math.hypot(gx,gy)
    if mg<1e-12:return
    ux,uy=gx/mg,gy/mg
    ax.annotate("",xy=(x,y),xytext=(x-ux*L,y-uy*L),arrowprops=dict(arrowstyle="-|>",color="crimson",lw=1.5),zorder=4)
    ax.text(x-ux*L*1.15,y-uy*L*1.15,lbl,color="crimson",fontsize=7,ha="center",va="center",zorder=4)
def _marrow(ax,x,y,m,sz,lbl):
    if abs(m)<1e-12:return
    t1,t2=(20,290)if m>0 else(290,20)
    ax.add_patch(Arc((x,y),sz,sz,angle=0,theta1=t1,theta2=t2,color="darkorange",lw=1.5,zorder=4))
    ea=math.radians(t2 if m>0 else t1)
    ax.annotate("",xy=(x+sz/2*math.cos(ea),y+sz/2*math.sin(ea)),
        xytext=(x+sz/2*math.cos(ea-.3),y+sz/2*math.sin(ea-.3)),
        arrowprops=dict(arrowstyle="-|>",color="darkorange",lw=1.5),zorder=4)
    ax.text(x+sz,y+sz,lbl,color="darkorange",fontsize=7,ha="center",va="center",zorder=4)
def _base_fig(d,title,show_loads=True):
    ext=_ext(d);fig,ax=plt.subplots(figsize=(7,6))
    for mid,m in d["members"].items():
        ni=d["nodes"][m["ni"]];nj=d["nodes"][m["nj"]]
        ax.plot([ni[0],nj[0]],[ni[1],nj[1]],color="black",lw=2,zorder=2)
        ax.text((ni[0]+nj[0])/2,(ni[1]+nj[1])/2,mid,fontsize=8,color="dimgray",ha="center",va="bottom",zorder=2)
    for nid,n in d["nodes"].items():
        ax.plot(n[0],n[1],"o",color="black",ms=4,zorder=3)
        ax.text(n[0],n[1],f" {nid}",fontsize=8,ha="left",va="bottom",zorder=3)
    sz=ext*_SF
    for nid,s in d["supports"].items():
        _dsup(ax,d["nodes"][nid][0],d["nodes"][nid][1],s,sz)
    if show_loads:
        AL=ext*_LF
        # nlx rows: (node_id, fx, fy, m)
        for nid,fx,fy,m2 in d["nlx"]:
            nx,ny=d["nodes"][nid]
            _farrow(ax,nx,ny,fx,fy,AL,f"{math.hypot(fx,fy):.3g}")
            _marrow(ax,nx,ny,m2,AL*.5,f"{m2:.3g}")
        # plx rows: (member_id, position, fx, fy, m, frame)
        for mid,pos,pfx,pfy,pm,pfr in d["plx"]:
            m=d["members"][mid];ni=d["nodes"][m["ni"]];nj=d["nodes"][m["nj"]]
            ang=math.atan2(nj[1]-ni[1],nj[0]-ni[0])
            px=ni[0]+math.cos(ang)*pos;py=ni[1]+math.sin(ang)*pos
            if pfr=="global":gx,gy=pfx,pfy
            else:c,s=math.cos(ang),math.sin(ang);gx,gy=c*pfx-s*pfy,s*pfx+c*pfy
            _farrow(ax,px,py,gx,gy,AL,f"{math.hypot(gx,gy):.3g}")
            _marrow(ax,px,py,pm,AL*.5,f"{pm:.3g}")
        # ulx rows: (member_id, start, end, wx, wy, frame)
        for mid,lo,hi,uwx,uwy,ufr in d["ulx"]:
            m=d["members"][mid];ni=d["nodes"][m["ni"]];nj=d["nodes"][m["nj"]]
            ang=math.atan2(nj[1]-ni[1],nj[0]-ni[0]);L=math.hypot(nj[0]-ni[0],nj[1]-ni[1])
            if ufr=="global":gx,gy=uwx,uwy
            else:c,s=math.cos(ang),math.sin(ang);gx,gy=c*uwx-s*uwy,s*uwx+c*uwy
            mg=math.hypot(gx,gy)
            if mg<1e-12:continue
            ux2,uy2=gx/mg,gy/mg;sl=AL*.6
            na=max(int((hi-lo)/max(L,1e-9)*8),3)
            txs,tys=[],[]
            for pos in np.linspace(lo,hi,na):
                x=ni[0]+math.cos(ang)*pos;y=ni[1]+math.sin(ang)*pos
                ax.annotate("",xy=(x,y),xytext=(x-ux2*sl,y-uy2*sl),arrowprops=dict(arrowstyle="-|>",color="steelblue",lw=1.),zorder=4)
                txs.append(x-ux2*sl);tys.append(y-uy2*sl)
            ax.plot(txs,tys,color="steelblue",lw=1.,zorder=4)
            ax.text(txs[na//2],tys[na//2],f"w={mg:.3g}",color="steelblue",fontsize=7,ha="center",va="bottom",zorder=4)
    xs_=[v[0]for v in d["nodes"].values()];ys_=[v[1]for v in d["nodes"].values()]
    mg=ext*.2;ax.set_xlim(min(xs_)-mg,max(xs_)+mg);ax.set_ylim(min(ys_)-mg,max(ys_)+mg)
    ax.set_aspect("equal",adjustable="datalim");ax.grid(True,linestyle=":",alpha=.5)
    ax.set_title(title);fig.tight_layout();return fig
def geometry_fig(d):return _base_fig(d,"Geometry, supports, and loads")
def deformed_fig(d):
    fig=_base_fig(d,f"Deformed shape (scale x{d['deformed_scale']:.3g})",show_loads=False)
    ax=fig.axes[0]
    for mid,df in d["deformed"].items():ax.plot(df["xg"],df["yg"],color="royalblue",lw=2,zorder=2.5)
    return fig
def member_fig(d,member_id):
    s=d["samples"][str(member_id)];m=d["members"][str(member_id)];xs=s["x"]
    fig,axes=plt.subplots(3,1,figsize=(7,7),sharex=True)
    for ax,key,lbl,col in zip(axes,("N","V","M"),("N (axial)","V (shear)","M (moment)"),("seagreen","steelblue","crimson")):
        y=s[key];ax.fill_between(xs,y,0.,color=col,alpha=.25);ax.plot(xs,y,color=col,lw=1.5)
        ax.axhline(0.,color="black",lw=.8);ax.set_ylabel(lbl);ax.grid(True,linestyle=":",alpha=.5)
    axes[-1].set_xlabel("Position along member (from node_i)")
    fig.suptitle(f"Member {member_id} ({m['ni']} -> {m['nj']})");fig.tight_layout();return fig
def run(d):
    gfig=geometry_fig(d);dfig=deformed_fig(d)
    mfig=lambda mid,_d=d:member_fig(_d,mid)
    return dict(geometry_fig=gfig,deformed_fig=dfig,member_fig=mfig)
