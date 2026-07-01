# Paste into Engine!B2. End with: _r=run(xl("Nodes"),xl("Members"),xl("Supports"),xl("NodalLoads"),xl("PointLoads"),xl("UDLs"));_r
import math,numpy as np,pandas as pd
def _nul(v):return v is None or(isinstance(v,float)and math.isnan(v))or str(v).strip()==""
_f=lambda v,d=0.:d if _nul(v)else float(v)
_fs=lambda v,d="local":d if _nul(v)else str(v).strip().lower()
def _b(v):
    if isinstance(v,bool):return v
    return not _nul(v)and str(v).strip().upper()in("TRUE","1","YES")
def _sup(t):
    return{"fixed":(1,1,1),"pinned":(1,1,0),"roller x":(1,0,0),"roller y":(0,1,0)}[str(t).strip().lower()]
def _ks(E,A,I,L):
    a=A*E/L;b=12*E*I/L**3;c=6*E*I/L**2;d=4*E*I/L;e=2*E*I/L
    return np.array([[a,0,0,-a,0,0],[0,b,c,0,-b,c],[0,c,d,0,-c,e],[-a,0,0,a,0,0],[0,-b,-c,0,b,-c],[0,c,e,0,-c,d]])
def _T(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,s,0,0,0,0],[-s,c,0,0,0,0],[0,0,1,0,0,0],[0,0,0,c,s,0],[0,0,0,-s,c,0],[0,0,0,0,0,1]])
def _toloc(fx,fy,fr,ang):
    if fr!="global":return fx,fy
    c,s=math.cos(ang),math.sin(ang);return c*fx+s*fy,-s*fx+c*fy
def _mlv(pts,udls,L,ang):
    f=np.zeros(6)
    for pos,pfx,pfy,pm,pfr in pts:
        px,py=_toloc(pfx,pfy,pfr,ang);r=pos/L
        h1=1-3*r**2+2*r**3;h2=r*(1-r)**2;h3=3*r**2-2*r**3;h4=r**2*(r-1)
        f+=np.array([px*(1-r),py*h1+pm*(-6*r+6*r**2)/L,py*L*h2+pm*(1-4*r+3*r**2),px*r,py*h3+pm*(6*r-6*r**2)/L,py*L*h4+pm*(-2*r+3*r**2)])
    for lo,hi,uwx,uwy,ufr in udls:
        wx,wy=_toloc(uwx,uwy,ufr,ang);r=np.linspace(lo/L,hi/L,41);dx=(hi-lo)/40
        w=np.ones(41)*dx;w[0]=w[-1]=dx/2
        h1=1-3*r**2+2*r**3;h2=r*(1-r)**2;h3=3*r**2-2*r**3;h4=r**2*(r-1)
        f+=np.array([np.dot(wx*(1-r),w),np.dot(wy*h1,w),np.dot(wy*L*h2,w),np.dot(wx*r,w),np.dot(wy*h3,w),np.dot(wy*L*h4,w)])
    return f
def _cond(k,f,hi,hj):
    rel=[i for i in([2]if hi else[])+([5]if hj else[])]
    if not rel:return k,f,list(range(6))
    ret=[i for i in range(6)if i not in rel]
    krc=k[np.ix_(ret,rel)];kci=np.linalg.inv(k[np.ix_(rel,rel)])
    ke=k[np.ix_(ret,ret)]-krc@kci@k[np.ix_(rel,ret)];fe=f[ret]-krc@kci@f[rel]
    kf=np.zeros((6,6));kf[np.ix_(ret,ret)]=ke;ff=np.zeros(6);ff[ret]=fe
    return kf,ff,ret
def _dofs(nids,nid):i=nids.index(nid);return[i*3,i*3+1,i*3+2]
def _solve_model(nodes,mems,sups,nlx,plx,ulx):
    nids=list(nodes);n=len(nids)*3;K=np.zeros((n,n));F=np.zeros(n)
    for l in nlx:
        ix=_dofs(nids,l["nid"]);F[ix]+=np.array([l["fx"],l["fy"],l["m"]])
    md={}
    for mid,m in mems.items():
        ni=nodes[m["ni"]];nj=nodes[m["nj"]]
        L=math.hypot(nj[0]-ni[0],nj[1]-ni[1]);ang=math.atan2(nj[1]-ni[1],nj[0]-ni[0])
        kl=_ks(m["E"],m["A"],m["I"],L)
        pts=[(p["pos"],p["fx"],p["fy"],p["m"],p["fr"])for p in plx if p["mid"]==mid]
        us=[(u["lo"],u["hi"],u["wx"],u["wy"],u["fr"])for u in ulx if u["mid"]==mid]
        feq=_mlv(pts,us,L,ang);kf,ff,ret=_cond(kl,feq,m["hi"],m["hj"])
        T=_T(ang);kg=T.T@kf@T;fg=T.T@ff
        ix=_dofs(nids,m["ni"])+_dofs(nids,m["nj"])
        F[ix]+=fg;K[np.ix_(ix,ix)]+=kg
        md[mid]=dict(L=L,ang=ang,kl=kl,feq=feq,kf=kf,ff=ff,T=T,ix=ix,ret=ret)
    rst=np.zeros(n,dtype=bool)
    for nid,s in sups.items():
        for f2,d2 in zip(s,_dofs(nids,nid)):
            if f2:rst[d2]=True
    hss=~np.isclose(K,0).all(axis=1);inact=~hss&~rst;free=~rst&~inact
    Kff=K[np.ix_(free,free)];Ff=F[free]-K[np.ix_(free,rst)]@np.zeros(rst.sum())
    if Kff.size and np.linalg.cond(Kff)>1e13:raise RuntimeError("Unstable structure -- check supports/hinges")
    Uf=np.linalg.solve(Kff,Ff);U=np.zeros(n);U[free]=Uf
    Rfull=np.zeros(n);Rfull[rst]=K[np.ix_(rst,free)]@Uf-F[rst]
    displ={nid:tuple(U[_dofs(nids,nid)])for nid in nids}
    react={nid:tuple(Rfull[_dofs(nids,nid)])for nid in sups}
    mst={}
    for mid,m in mems.items():
        d=md[mid];dl=d["T"]@U[d["ix"]];ef=d["kf"]@dl-d["ff"]
        rel=[i for i in range(6)if i not in d["ret"]]
        th=dict(zip(rel,np.linalg.solve(d["kl"][np.ix_(rel,rel)],d["feq"][rel]-d["kl"][np.ix_(rel,d["ret"])]@dl[d["ret"]])))if rel else{}
        mst[mid]=dict(L=d["L"],ang=d["ang"],ef=ef,dl=dl,t1=th.get(2,dl[2]),t2=th.get(5,dl[5]),E=m["E"],A=m["A"],I=m["I"])
    return displ,react,mst
def _sample(ms,pts,us,n=80):
    L=ms["L"];Q=ms["ef"];eps=max(L*1e-9,1e-12);ang=ms["ang"]
    bp={0.,L}
    for p in pts:bp|={p[0],max(0,p[0]-eps),min(L,p[0]+eps)}
    for u in us:bp|={u[0],u[1]}
    xs=np.array(sorted(bp|set(np.linspace(0,L,n).tolist())))
    N=np.full_like(xs,Q[0]);V=np.full_like(xs,Q[1]);M=-Q[2]+Q[1]*xs
    for pos,pfx,pfy,pm,pfr in pts:
        fx,fy=_toloc(pfx,pfy,pfr,ang)
        a=xs>pos+eps/2;N[a]+=fx;V[a]+=fy;M[a]+=fy*(xs[a]-pos)-pm
    for lo,hi,uwx,uwy,ufr in us:
        wx,wy=_toloc(uwx,uwy,ufr,ang)
        b=np.clip(xs,lo,hi)-lo;N+=wx*b;V+=wy*b;M+=wy*(xs*b-(np.clip(xs,lo,hi)**2-lo**2)/2)
    dx=np.diff(xs);ct=lambda y:np.concatenate([[0],np.cumsum((y[:-1]+y[1:])/2*dx)])
    slp=ms["t1"]+ct(M/(ms["E"]*ms["I"]))
    return dict(x=xs,N=N,V=V,M=M,defl=ms["dl"][1]+ct(slp),axial=ms["dl"][0]+ct(N/(ms["E"]*ms["A"])))
def run(nodes_df,members_df,supports_df,nodal_loads_df,point_loads_df,udls_df):
    nds={}
    for r in nodes_df.itertuples(index=False):
        if _nul(r[0]):continue
        nds[str(r[0])]=(float(r[1]),float(r[2]))
    mems={}
    for r in members_df.itertuples(index=False):
        if _nul(r[0]):continue
        mems[str(r[0])]=dict(ni=str(r[1]),nj=str(r[2]),E=float(r[3]),A=float(r[4]),I=float(r[5]),hi=_b(r[6]),hj=_b(r[7]))
    sups={}
    for r in supports_df.itertuples(index=False):
        if _nul(r[0]):continue
        sups[str(r[0])]=_sup(r[1])
    nlx=[]
    for r in nodal_loads_df.itertuples(index=False):
        if _nul(r[0]):continue
        nlx.append(dict(nid=str(r[0]),fx=_f(r[1]),fy=_f(r[2]),m=_f(r[3])))
    plx=[]
    for r in point_loads_df.itertuples(index=False):
        if _nul(r[0]):continue
        plx.append(dict(mid=str(r[0]),pos=float(r[1]),fx=_f(r[2]),fy=_f(r[3]),m=_f(r[4]),fr=_fs(r[5])))
    ulx=[]
    for r in udls_df.itertuples(index=False):
        if _nul(r[0]):continue
        ni=nds[mems[str(r[0])]["ni"]];nj=nds[mems[str(r[0])]["nj"]];L=math.hypot(nj[0]-ni[0],nj[1]-ni[1])
        ulx.append(dict(mid=str(r[0]),wx=_f(r[1]),wy=_f(r[2]),fr=_fs(r[3]),lo=_f(r[4]),hi=_f(r[5],L)))
    displ,react,mst=_solve_model(nds,mems,sups,nlx,plx,ulx)
    rdf=pd.DataFrame([[nid,*react[nid]]for nid in sups],columns=["node_id","Rx","Ry","Rm"])
    ddf=pd.DataFrame([[nid,*displ[nid]]for nid in nds],columns=["node_id","Ux","Uy","Rz"])
    xs_=[v[0]for v in nds.values()];ys_=[v[1]for v in nds.values()]
    ext=max(max(xs_)-min(xs_),max(ys_)-min(ys_),1e-9)
    pts_m={mid:[(p["pos"],p["fx"],p["fy"],p["m"],p["fr"])for p in plx if p["mid"]==mid]for mid in mems}
    us_m={mid:[(u["lo"],u["hi"],u["wx"],u["wy"],u["fr"])for u in ulx if u["mid"]==mid]for mid in mems}
    mx=0.
    for mid,ms in mst.items():
        s=_sample(ms,pts_m[mid],us_m[mid]);mx=max(mx,np.abs(s["defl"]).max(),np.abs(s["axial"]).max())
    sc=0.1*ext/mx if mx>1e-12 else 1.
    smp={};dfm={}
    for mid,ms in mst.items():
        s=_sample(ms,pts_m[mid],us_m[mid]);smp[mid]=s
        ni=nds[mems[mid]["ni"]];ang=ms["ang"];c,s2=math.cos(ang),math.sin(ang)
        xl=s["x"]+sc*s["axial"];yl=sc*s["defl"]
        dfm[mid]=dict(xg=ni[0]+c*xl-s2*yl,yg=ni[1]+s2*xl+c*yl)
    return dict(reactions=rdf,displacements=ddf,nodes=nds,members=mems,supports=sups,
        nlx=nlx,plx=plx,ulx=ulx,samples=smp,deformed=dfm,deformed_scale=sc)
