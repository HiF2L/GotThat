import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.ontology import (
    Domain,
    Track,
    Concept,
    ConceptDependency,
    DependencyType,
    AssessmentItem,
    AssessmentType,
)
from app.models.mastery import User, UserTrackEnrollment, UserMasteryState


async def seed_initial_knowledge_graph(session: AsyncSession):
    """
    Populates the database with the initial curriculum matching the video demonstration:
    - Differential Forms & Advanced Calculus
    - Real assessment questions (Line integrals, Stokes, Covectors, Wedge product)
    """
    # Check if already seeded
    existing = await session.execute(select(Domain).where(Domain.slug == "physics_math"))
    if existing.scalars().first():
        return

    # 1. Create Domain
    domain = Domain(
        id=str(uuid.uuid4()),
        slug="physics_math",
        title="Mathematics & Theoretical Physics",
        description="From Vector Calculus to Differential Forms and Unified Field Theories.",
    )
    session.add(domain)

    # 2. Create Track
    track = Track(
        id=str(uuid.uuid4()),
        domain_id=domain.id,
        slug="differential_forms",
        title="Differential Forms & Electromagnetism",
        icon_url="https://cdn-icons-png.flaticon.com/512/3749/3749784.png",
    )
    session.add(track)

    # 3. Create Concepts (in dependency order)
    concepts_data = [
        {
            "code": "MATH.VEC.LINE_INT",
            "title": "Line Integrals in Vector Fields",
            "summary": "Integrating a vector field along a curve: $\\int_C \\mathbf{F} \\cdot d\\mathbf{r}$, computing mechanical work done along a path.",
            "bloom": "apply",
        },
        {
            "code": "MATH.VEC.DIV_CURL",
            "title": "Divergence and Curl",
            "summary": "Flux density and rotational circulation of 3D vector fields: $\\nabla \\cdot \\mathbf{F}$ and $\\nabla \\times \\mathbf{F}$.",
            "bloom": "understand",
        },
        {
            "code": "MATH.VEC.STOKES",
            "title": "Classical Stokes' Theorem",
            "summary": "Relating the curl over an open surface to the boundary line integral: $\\iint_S (\\nabla \\times \\mathbf{F}) \\cdot d\\mathbf{S} = \\oint_{\\partial S} \\mathbf{F} \\cdot d\\mathbf{r}$.",
            "bloom": "apply",
        },
        {
            "code": "MATH.LA.COVECTORS",
            "title": "Dual Vectors (Covectors / 1-Forms)",
            "summary": "Linear functionals mapping vectors to scalars: $\\alpha(\\mathbf{v}) \\in \\mathbb{R}$. Geometrically represented as parallel oriented hyperplanes.",
            "bloom": "analyze",
        },
        {
            "code": "MATH.DF.COV_FIELD",
            "title": "Covector Fields & Differential 1-Forms",
            "summary": "A smooth assignment of a covector to each point in space. Integration along curves naturally eats 1-forms.",
            "bloom": "understand",
        },
        {
            "code": "MATH.DF.WEDGE",
            "title": "Wedge Product & Alternating Tensors",
            "summary": "Antisymmetric exterior product $\\alpha \\wedge \\beta = -(\\beta \\wedge \\alpha)$, measuring oriented oriented multi-dimensional volume/flux.",
            "bloom": "apply",
        },
        {
            "code": "MATH.DF.EXT_DERIV",
            "title": "Exterior Derivative (d operator)",
            "summary": "Unified differential operator $d$ mapping $k$-forms to $(k+1)$-forms with the fundamental identity $d^2 = 0$.",
            "bloom": "evaluate",
        },
        {
            "code": "MATH.DF.GEN_STOKES",
            "title": "Generalized Stokes' Theorem",
            "summary": "The master equation of geometry and calculus: $\\int_{\\partial \\Omega} \\omega = \\int_\\Omega d\\omega$.",
            "bloom": "evaluate",
        },
    ]

    concept_objs = {}
    for c in concepts_data:
        obj = Concept(
            id=str(uuid.uuid4()),
            track_id=track.id,
            code=c["code"],
            title=c["title"],
            summary=c["summary"],
            bloom_level=c["bloom"],
        )
        session.add(obj)
        concept_objs[c["code"]] = obj

    # 4. Create Dependencies (Edges)
    deps = [
        ("MATH.VEC.LINE_INT", "MATH.VEC.DIV_CURL"),
        ("MATH.VEC.DIV_CURL", "MATH.VEC.STOKES"),
        ("MATH.VEC.LINE_INT", "MATH.LA.COVECTORS"),
        ("MATH.LA.COVECTORS", "MATH.DF.COV_FIELD"),
        ("MATH.DF.COV_FIELD", "MATH.DF.WEDGE"),
        ("MATH.DF.WEDGE", "MATH.DF.EXT_DERIV"),
        ("MATH.VEC.STOKES", "MATH.DF.GEN_STOKES"),
        ("MATH.DF.EXT_DERIV", "MATH.DF.GEN_STOKES"),
    ]

    for src_code, dst_code in deps:
        dep = ConceptDependency(
            id=str(uuid.uuid4()),
            source_concept_id=concept_objs[src_code].id,
            target_concept_id=concept_objs[dst_code].id,
            relation_type=DependencyType.STRICT_PREREQUISITE,
        )
        session.add(dep)

    # 5. Create Assessment Items (Quizzes directly matching video items)
    assessment_data = [
        {
            "concept_code": "MATH.VEC.LINE_INT",
            "prompt": "A force field $\\mathbf{F}$ acts on a particle as it moves along a curve $C$. What does the line integral $\\int_C \\mathbf{F} \\cdot d\\mathbf{r}$ compute?",
            "options": [
                {"id": "a", "text": "The potential energy difference (only for conservative fields)", "is_correct": False},
                {"id": "b", "text": "The net flux escaping through the normal of the curve", "is_correct": False},
                {"id": "c", "text": "The net work done by the field on the particle along the path", "is_correct": True, "explanation": "The line integral of a vector field along a curve computes the cumulative work $\\int \\mathbf{F} \\cdot d\\mathbf{r}$."},
                {"id": "d", "text": "The total path length scaled by mass", "is_correct": False},
            ],
            "difficulty": 0.3,
        },
        {
            "concept_code": "MATH.LA.COVECTORS",
            "prompt": "Let covector $\\alpha = 3 dx - 2 dy$ and vector $\\mathbf{v} = \\begin{pmatrix} 2 \\\\ 5 \\end{pmatrix}$. What is the evaluation $\\alpha(\\mathbf{v})$?",
            "options": [
                {"id": "a", "text": "$-4$", "is_correct": True, "explanation": "$\\alpha(\\mathbf{v}) = 3(2) - 2(5) = 6 - 10 = -4$."},
                {"id": "b", "text": "$16$", "is_correct": False},
                {"id": "c", "text": "$-1$", "is_correct": False},
                {"id": "d", "text": "A new 2D vector $\\begin{pmatrix} 6 \\\\ -10 \\end{pmatrix}$", "is_correct": False},
            ],
            "difficulty": 0.5,
        },
        {
            "concept_code": "MATH.DF.WEDGE",
            "prompt": "Why is the wedge product of identical 1-forms identically zero: $\\mathbf{v} \\wedge \\mathbf{v} = 0$?",
            "options": [
                {"id": "a", "text": "Due to antisymmetry: $\\mathbf{u} \\wedge \\mathbf{v} = -(\\mathbf{v} \\wedge \\mathbf{u})$, setting $\\mathbf{u}=\\mathbf{v}$ yields $X = -X \\implies 2X = 0$", "is_correct": True, "explanation": "Antisymmetry guarantees that any wedge of a form with itself vanishes, geometrically representing zero oriented area."},
                {"id": "b", "text": "Because vectors have zero Euclidean magnitude when multiplied", "is_correct": False},
                {"id": "c", "text": "Only true in even-dimensional manifolds", "is_correct": False},
                {"id": "d", "text": "Because differentials $dx$ cannot be squared", "is_correct": False},
            ],
            "difficulty": 0.6,
        },
    ]

    for item in assessment_data:
        a_obj = AssessmentItem(
            id=str(uuid.uuid4()),
            concept_id=concept_objs[item["concept_code"]].id,
            item_type=AssessmentType.SINGLE_CHOICE,
            prompt_markdown=item["prompt"],
            options=item["options"],
            difficulty=item["difficulty"],
        )
        session.add(a_obj)

    # 6. Create Default Demo User
    demo_user = User(
        id=str(uuid.uuid4()),
        username="hitori_learner",
        email="learner@gotit.local",
    )
    session.add(demo_user)

    enrollment = UserTrackEnrollment(
        id=str(uuid.uuid4()),
        user_id=demo_user.id,
        track_id=track.id,
        is_active_in_feed=True,
    )
    session.add(enrollment)

    await session.commit()
