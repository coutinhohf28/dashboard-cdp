"""Fila de conferência do cadastro de parceiros do DI."""
import streamlit as st


def abrir_caso(caso):
    st.session_state.revisao_aberta = (int(caso.id), int(caso.versao))


def exibir_conferencia(consultar, gravar, editar, usuario):
    if msg := st.session_state.pop("aviso_ficha", None):
        st.success(msg)
    if msg := st.session_state.pop("aviso_revisao", None):
        st.success(msg)
    casos = consultar("""
        SELECT c.*, COALESCE((SELECT string_agg(p.nome_instituicao, ' / ' ORDER BY x.ord)
            FROM unnest(c.parceiros) WITH ORDINALITY x(id,ord)
            JOIN public.parceiro p ON p.id_parceiro=x.id), 'Cadastro indisponível') AS cadastro
        FROM di_private.conferencia_cadastro c ORDER BY c.id
    """)
    if "id" not in casos:
        return
    c1, c2 = st.columns(2)
    tipo = c1.selectbox("Tipo de pendência", ["Todos", "Duplicidade", "Nome incompleto", "Categoria"])
    situacao = c2.selectbox("Situação da revisão", ["A conferir", "Precisa de confirmação", "Concluído", "Todas"])
    busca = st.text_input("Buscar na conferência", placeholder="Nome ou número do cadastro").strip()
    filtrados = casos
    if tipo != "Todos":
        filtrados = filtrados[filtrados.tipo == tipo]
    if situacao != "Todas":
        filtrados = filtrados[filtrados.situacao == situacao]
    if busca:
        por_nome = filtrados.cadastro.str.contains(busca, case=False, regex=False)
        codigo = busca.lstrip("#")
        if codigo.isdecimal():
            por_nome |= filtrados.parceiros.map(lambda ids: int(codigo) in ids)
        filtrados = filtrados[por_nome]
    filtro = (tipo, situacao, busca)
    if st.session_state.get("revisao_filtro") != filtro:
        st.session_state.revisao_filtro = filtro
        st.session_state.revisao_pagina = 0
        st.session_state.pop("revisao_aberta", None)
    itens = list(filtrados.itertuples(index=False))
    if not itens:
        st.info("Nenhum cadastro para esses filtros.")
        return
    aberto = st.session_state.get("revisao_aberta")
    pos = next((i for i, item in enumerate(itens) if aberto and item.id == aberto[0]), None)
    if pos is None:
        pagina = min(st.session_state.get("revisao_pagina", 0), (len(itens)-1)//8)
        st.caption(f"{len(itens)} pendências · Página {pagina+1} de {(len(itens)-1)//8+1}")
        for item in itens[pagina*8:pagina*8+8]:
            if st.button(item.cadastro, key=f"abrir_revisao_{item.id}", use_container_width=True,
                         help=item.motivo):
                abrir_caso(item)
                st.rerun()
        anterior, seguinte = st.columns(2)
        if anterior.button("Página anterior", disabled=pagina == 0):
            st.session_state.revisao_pagina = pagina-1
            st.rerun()
        if seguinte.button("Página seguinte", disabled=(pagina+1)*8 >= len(itens)):
            st.session_state.revisao_pagina = pagina+1
            st.rerun()
        return

    caso = itens[pos]
    if st.button("← Voltar à lista"):
        st.session_state.pop("revisao_aberta", None)
        st.session_state.revisao_pagina = pos//8
        st.rerun()
    st.subheader(caso.cadastro)
    st.caption(f"{caso.tipo} · {caso.situacao}")
    st.write(caso.motivo)
    if caso.responsavel:
        st.caption(f"Última decisão por {caso.responsavel}")
    if caso.comentario:
        st.info(caso.comentario)
    if caso.versao != aberto[1]:
        st.warning("Outra pessoa atualizou esta revisão. Confira a decisão antes de continuar.")
        if st.button("Carregar revisão atualizada"):
            abrir_caso(caso)
            st.rerun()
        return
    fichas = consultar("""SELECT p.*, p.xmin::text AS versao FROM public.parceiro p
                          WHERE id_parceiro = ANY(%s) ORDER BY nome_instituicao""", (list(caso.parceiros),))
    if not fichas.empty:
        nomes = dict(zip(fichas.id_parceiro, fichas.nome_instituicao))
        codigo = next(iter(nomes)) if len(nomes)==1 else st.selectbox(
            "Ficha do grupo", list(nomes), format_func=lambda i: f"{nomes[i]} · #{i}", key=f"grupo_{caso.id}")
        editar(int(codigo), fichas.loc[fichas.id_parceiro == codigo].iloc[0])
    st.markdown("**Decisão da revisão**")
    with st.form(f"decisao_{caso.id}_{caso.versao}"):
        comentario = st.text_area("Observação para a equipe", value=caso.comentario)
        a, b = st.columns(2)
        concluir = a.form_submit_button("Concluir e avançar", type="primary")
        confirmar = b.form_submit_button("Precisa de confirmação")
    if concluir or confirmar:
        if confirmar and not comentario.strip():
            st.warning("Descreva o que precisa ser confirmado.")
            return
        destino = "Concluído" if concluir else "Precisa de confirmação"
        alterados = gravar("""UPDATE di_private.conferencia_cadastro SET situacao=%s, comentario=%s,
            responsavel=%s, atualizado_em=now(), versao=versao+1 WHERE id=%s AND versao=%s""",
            (destino, comentario.strip(), usuario, int(caso.id), int(caso.versao)))
        if alterados == 1:
            st.session_state.aviso_revisao = f"Revisão registrada como {destino.lower()}."
            if pos+1 < len(itens):
                abrir_caso(itens[pos+1])
            else:
                st.session_state.pop("revisao_aberta", None)
            st.rerun()
        elif alterados == 0:
            st.warning("Outra pessoa já atualizou esta revisão. Reabra a ficha.")
