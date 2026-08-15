-- Fatia 4: centroides (cidade/país/fuso) para o mapa. Sem GPS, sem IP.
-- Coordenadas arredondadas a 4 casas (~11 m). Pins só a partir de agregados.

CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS public.geo_centroids (
    kind     TEXT NOT NULL CHECK (kind IN ('country', 'city', 'tz')),
    country  TEXT,
    name     TEXT NOT NULL,
    lat      NUMERIC(8,4) NOT NULL,
    lon      NUMERIC(8,4) NOT NULL,
    UNIQUE (kind, country, name)
);

COMMENT ON TABLE public.geo_centroids IS
    'Centroides aproximados para o mapa de audiência. Nunca posição do aparelho.';

CREATE OR REPLACE FUNCTION public._geo_norm(t TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT lower(trim(regexp_replace(unaccent(COALESCE(t, '')), '\s+', ' ', 'g')));
$$;

INSERT INTO public.geo_centroids (kind, country, name, lat, lon) VALUES
-- países
('country', 'BR', 'brasil', -14.2350, -51.9253),
('country', 'US', 'united states', 39.8283, -98.5795),
('country', 'PT', 'portugal', 39.3999, -8.2245),
('country', 'AR', 'argentina', -38.4161, -63.6167),
('country', 'UY', 'uruguay', -32.5228, -55.7658),
('country', 'PY', 'paraguay', -23.4425, -58.4438),
('country', 'CL', 'chile', -35.6751, -71.5430),
('country', 'BO', 'bolivia', -16.2902, -63.5887),
('country', 'PE', 'peru', -9.1900, -75.0152),
('country', 'CO', 'colombia', 4.5709, -74.2973),
('country', 'MX', 'mexico', 23.6345, -102.5528),
('country', 'ES', 'spain', 40.4637, -3.7492),
('country', 'DE', 'germany', 51.1657, 10.4515),
('country', 'FR', 'france', 46.2276, 2.2137),
('country', 'IT', 'italy', 41.8719, 12.5674),
('country', 'GB', 'united kingdom', 55.3781, -3.4360),
('country', 'JP', 'japan', 36.2048, 138.2529),
('country', 'CN', 'china', 35.8617, 104.1954),
('country', 'IN', 'india', 20.5937, 78.9629),
('country', 'AU', 'australia', -25.2744, 133.7751),
('country', 'CA', 'canada', 56.1304, -106.3468),
-- SC / Vale
('city', 'BR', 'blumenau', -26.9194, -49.0661),
('city', 'BR', 'indaial', -26.8978, -49.2317),
('city', 'BR', 'timbo', -26.8228, -49.2747),
('city', 'BR', 'pomerode', -26.7406, -49.1769),
('city', 'BR', 'gaspar', -26.9314, -48.9589),
('city', 'BR', 'brusque', -27.0977, -48.9107),
('city', 'BR', 'itajai', -26.9078, -48.6619),
('city', 'BR', 'balneario camboriu', -26.9926, -48.6352),
('city', 'BR', 'joinville', -26.3045, -48.8487),
('city', 'BR', 'florianopolis', -27.5954, -48.5480),
('city', 'BR', 'rio do sul', -27.2156, -49.6430),
('city', 'BR', 'ibirama', -27.0547, -49.5192),
('city', 'BR', 'presidente getulio', -27.0519, -49.6228),
('city', 'BR', 'lontras', -27.1661, -49.5420),
('city', 'BR', 'apiuna', -27.0375, -49.3886),
('city', 'BR', 'ascurra', -26.9564, -49.3783),
('city', 'BR', 'rodeio', -26.9244, -49.3664),
('city', 'BR', 'benedito novo', -26.7814, -49.3594),
('city', 'BR', 'doutor pedrinho', -26.7147, -49.4819),
('city', 'BR', 'taio', -27.1211, -49.9986),
('city', 'BR', 'ituporanga', -27.4139, -49.6025),
('city', 'BR', 'chapeco', -27.1004, -52.6152),
('city', 'BR', 'criciuma', -28.6775, -49.3697),
('city', 'BR', 'lages', -27.8150, -50.3259),
('city', 'BR', 'jaragua do sul', -26.4851, -49.0713),
-- capitais BR
('city', 'BR', 'sao paulo', -23.5505, -46.6333),
('city', 'BR', 'rio de janeiro', -22.9068, -43.1729),
('city', 'BR', 'brasilia', -15.7975, -47.8919),
('city', 'BR', 'belo horizonte', -19.9167, -43.9345),
('city', 'BR', 'curitiba', -25.4284, -49.2733),
('city', 'BR', 'porto alegre', -30.0346, -51.2177),
('city', 'BR', 'salvador', -12.9714, -38.5014),
('city', 'BR', 'recife', -8.0476, -34.8770),
('city', 'BR', 'fortaleza', -3.7172, -38.5433),
('city', 'BR', 'manaus', -3.1190, -60.0217),
('city', 'BR', 'belem', -1.4558, -48.4902),
('city', 'BR', 'goiania', -16.6869, -49.2648),
('city', 'BR', 'cuiaba', -15.6014, -56.0979),
('city', 'BR', 'campo grande', -20.4697, -54.6201),
('city', 'BR', 'vitoria', -20.3155, -40.3128),
('city', 'BR', 'natal', -5.7945, -35.2110),
('city', 'BR', 'joao pessoa', -7.1195, -34.8450),
('city', 'BR', 'maceio', -9.6498, -35.7089),
('city', 'BR', 'aracaju', -10.9472, -37.0731),
('city', 'BR', 'teresina', -5.0892, -42.8016),
('city', 'BR', 'sao luis', -2.5307, -44.3068),
('city', 'BR', 'palmas', -10.2491, -48.3243),
('city', 'BR', 'porto velho', -8.7612, -63.9004),
('city', 'BR', 'rio branco', -9.9754, -67.8249),
('city', 'BR', 'boa vista', 2.8235, -60.6758),
('city', 'BR', 'macapa', 0.0349, -51.0694),
-- fusos → centroide do país (fallback quando não há cidade)
('tz', 'BR', 'america/sao_paulo', -14.2350, -51.9253),
('tz', 'BR', 'america/fortaleza', -14.2350, -51.9253),
('tz', 'BR', 'america/recife', -14.2350, -51.9253),
('tz', 'BR', 'america/bahia', -14.2350, -51.9253),
('tz', 'BR', 'america/belem', -14.2350, -51.9253),
('tz', 'BR', 'america/manaus', -14.2350, -51.9253),
('tz', 'BR', 'america/cuiaba', -14.2350, -51.9253),
('tz', 'BR', 'america/porto_velho', -14.2350, -51.9253),
('tz', 'BR', 'america/rio_branco', -14.2350, -51.9253),
('tz', 'BR', 'america/noronha', -3.8540, -32.4230),
('tz', 'US', 'america/new_york', 39.8283, -98.5795),
('tz', 'US', 'america/chicago', 39.8283, -98.5795),
('tz', 'US', 'america/denver', 39.8283, -98.5795),
('tz', 'US', 'america/los_angeles', 39.8283, -98.5795),
('tz', 'PT', 'europe/lisbon', 39.3999, -8.2245),
('tz', 'ES', 'europe/madrid', 40.4637, -3.7492),
('tz', 'GB', 'europe/london', 55.3781, -3.4360),
('tz', 'AR', 'america/argentina/buenos_aires', -38.4161, -63.6167)
ON CONFLICT (kind, country, name) DO UPDATE
SET lat = EXCLUDED.lat, lon = EXCLUDED.lon;

CREATE OR REPLACE FUNCTION public.get_admin_listen_map(p_days INTEGER DEFAULT 30)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_days INTEGER := LEAST(GREATEST(COALESCE(p_days, 30), 1), 365);
    v_from DATE := (timezone('America/Sao_Paulo', NOW()))::date - (v_days - 1);
BEGIN
    IF NOT public.is_admin_user() THEN
        RETURN jsonb_build_object('ok', FALSE, 'error', 'Acesso negado: requer role admin');
    END IF;

    RETURN jsonb_build_object(
        'ok', TRUE,
        'days', v_days,
        'from', v_from,
        'unmapped', (
            SELECT COUNT(*)::int
            FROM public.listen_events e
            WHERE e.day >= v_from
              AND NOT EXISTS (
                  SELECT 1 FROM public.geo_centroids c
                  WHERE (c.kind = 'city' AND e.city IS NOT NULL AND public._geo_norm(c.name) = public._geo_norm(e.city)
                         AND (e.country IS NULL OR e.country = '' OR c.country = e.country))
                     OR (c.kind = 'country' AND e.country IS NOT NULL AND e.country <> '' AND c.country = e.country)
                     OR (c.kind = 'tz' AND e.tz IS NOT NULL AND public._geo_norm(c.name) = public._geo_norm(e.tz))
              )
        ),
        'points', COALESCE((
            SELECT jsonb_agg(row_to_json(p)::jsonb ORDER BY p.plays DESC)
            FROM (
                SELECT
                    r.lat, r.lon, r.level, r.label,
                    SUM(r.plays)::int AS plays
                FROM (
                    SELECT
                        a.plays,
                        COALESCE(ci.lat, co.lat, tz.lat) AS lat,
                        COALESCE(ci.lon, co.lon, tz.lon) AS lon,
                        CASE
                            WHEN ci.lat IS NOT NULL THEN 'city'
                            WHEN co.lat IS NOT NULL THEN 'country'
                            WHEN tz.lat IS NOT NULL THEN 'tz'
                        END AS level,
                        CASE
                            WHEN ci.lat IS NOT NULL THEN
                                COALESCE(NULLIF(a.city, ''), ci.name) ||
                                CASE WHEN COALESCE(a.country, ci.country, '') <> ''
                                     THEN ' (' || COALESCE(a.country, ci.country) || ')' ELSE '' END
                            WHEN co.lat IS NOT NULL THEN COALESCE(NULLIF(a.country, ''), co.country)
                            WHEN tz.lat IS NOT NULL THEN COALESCE(NULLIF(a.tz, ''), tz.name)
                        END AS label
                    FROM (
                        SELECT
                            NULLIF(country, '') AS country,
                            NULLIF(city, '') AS city,
                            NULLIF(tz, '') AS tz,
                            COUNT(*)::int AS plays
                        FROM public.listen_events
                        WHERE day >= v_from
                        GROUP BY 1, 2, 3
                    ) a
                    LEFT JOIN public.geo_centroids ci
                      ON ci.kind = 'city'
                     AND a.city IS NOT NULL
                     AND public._geo_norm(ci.name) = public._geo_norm(a.city)
                     AND (a.country IS NULL OR ci.country = a.country)
                    LEFT JOIN public.geo_centroids co
                      ON co.kind = 'country'
                     AND a.country IS NOT NULL
                     AND co.country = a.country
                    LEFT JOIN public.geo_centroids tz
                      ON tz.kind = 'tz'
                     AND a.tz IS NOT NULL
                     AND public._geo_norm(tz.name) = public._geo_norm(a.tz)
                ) r
                WHERE r.lat IS NOT NULL
                GROUP BY r.lat, r.lon, r.level, r.label
            ) p
        ), '[]'::jsonb)
    );
END;
$$;

COMMENT ON FUNCTION public.get_admin_listen_map(INTEGER) IS
    'Pontos agregados (cidade → país → fuso) para o mapa Leaflet. Só admin.';

GRANT EXECUTE ON FUNCTION public.get_admin_listen_map(INTEGER) TO anon;
GRANT EXECUTE ON FUNCTION public.get_admin_listen_map(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_admin_listen_map(INTEGER) TO service_role;
